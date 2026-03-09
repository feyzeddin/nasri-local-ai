#!/usr/bin/env bash
# =============================================================================
#  Nasri Akıllı Kurulum Scripti
#  - Ön gereksinimleri otomatik kurar (Redis, Ollama, Python, pip)
#  - Port çakışmalarını tespit eder ve çözer
#  - Her adımda hata kontrolü yapar
#  - Hata durumunda kural tabanlı otomatik onarım uygular
#  - Ollama hazırsa AI destekli tanı da yapar
# =============================================================================
set -uo pipefail

# --- Renkler ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${BLUE}[nasri]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
step() { echo -e "\n${CYAN}══════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}══════════════════════════════════════${NC}"; }

# --- Yapılandırma ---
NASRI_HOME="${NASRI_HOME:-$HOME/.nasri}"
NASRI_SRC="$NASRI_HOME/src"
NASRI_VENV="$NASRI_HOME/venv"
NASRI_DATA_DIR="$NASRI_HOME/data"
NASRI_LOG="$NASRI_HOME/install.log"
REPO_URL="${NASRI_REPO_URL:-https://github.com/feyzeddin/nasri-local-ai.git}"
OLLAMA_MODEL="${NASRI_MODEL:-llama3}"
API_PORT="${NASRI_API_PORT:-8000}"
MAX_RETRY=3

mkdir -p "$NASRI_HOME" "$NASRI_DATA_DIR"
exec > >(tee -a "$NASRI_LOG") 2>&1

# =============================================================================
# KULLANICI ONAYI
# =============================================================================
python3 - <<'PYBOX'
Y  = '\033[1;33m'   # sarı
R  = '\033[0;31m'   # kırmızı
NC = '\033[0m'
W  = 62             # iç genişlik

def row(text='', text_color=''):
    pad = W - len(text)
    return f"{Y}║{NC}{text_color}{text}{NC}{' ' * pad}{Y}║{NC}"

sep_top = f"{Y}╔{'═' * W}╗{NC}"
sep_mid = f"{Y}╠{'═' * W}╣{NC}"
sep_bot = f"{Y}╚{'═' * W}╝{NC}"

print('')
print(sep_top)
print(row())
print(row('  ÖNEMLİ UYARI', R))
print(row())
print(sep_mid)
print(row())
print(row('  Nasri, bu cihazda TEK BAŞINA çalışmak üzere tasarlanmıştır.'))
print(row())
print(row('  Çalışan başka uygulama veya servisler varsa bunları'))
print(row('  durdurabilir ve silebilir.'))
print(row())
print(row('  Kuruluma devam etmeden önce bunu onaylıyor musunuz?'))
print(row())
print(sep_bot)
print('')
PYBOX

while true; do
    read -r -p "$(echo -e "${CYAN}Onaylıyor musunuz? [E/H]:${NC} ")" ONAY </dev/tty
    case "${ONAY^^}" in
        E|EVET)
            echo ""
            ok "Onaylandı. Kurulum başlıyor..."
            echo ""
            break
            ;;
        H|HAYIR)
            echo ""
            warn "Kurulum iptal edildi."
            exit 0
            ;;
        *)
            warn "Lütfen E (evet) veya H (hayır) girin."
            ;;
    esac
done

# =============================================================================
# YARDIMCI FONKSİYONLAR
# =============================================================================

retry() {
    local n=0
    until [ "$n" -ge "$MAX_RETRY" ]; do
        "$@" && return 0
        n=$((n+1))
        warn "Deneme $n/$MAX_RETRY başarısız, 5 saniye bekleniyor..."
        sleep 5
    done
    return 1
}

port_in_use() { ss -tlnp 2>/dev/null | grep -q ":$1 " || lsof -i ":$1" &>/dev/null; }

find_free_port() {
    local port="$1"
    while port_in_use "$port"; do
        warn "Port $port kullanımda, $((port+1)) deneniyor..."
        port=$((port+1))
    done
    echo "$port"
}

command_exists() { command -v "$1" &>/dev/null; }

# Kural tabanlı otomatik onarım
rule_based_heal() {
    local error_msg="$1"
    log "Hata analiz ediliyor: $error_msg"

    if echo "$error_msg" | grep -q "No module named"; then
        local mod
        mod=$(echo "$error_msg" | grep -oP "No module named '\K[^']+")
        warn "Eksik Python modülü tespit edildi: $mod"
        warn "Yükleniyor: $mod"
        "$NASRI_VENV/bin/pip" install "$mod" && return 0
    fi

    if echo "$error_msg" | grep -q "address already in use\|Address already in use"; then
        warn "Port çakışması tespit edildi"
        API_PORT=$(find_free_port "$API_PORT")
        ok "Yeni port: $API_PORT"
        export NASRI_API_PORT="$API_PORT"
        # .env dosyasına yaz
        if [ -f "$NASRI_SRC/project/nasri-core/.env" ]; then
            sed -i "s/^NASRI_API_PORT=.*/NASRI_API_PORT=$API_PORT/" "$NASRI_SRC/project/nasri-core/.env" 2>/dev/null || \
            echo "NASRI_API_PORT=$API_PORT" >> "$NASRI_SRC/project/nasri-core/.env"
        fi
        return 0
    fi

    if echo "$error_msg" | grep -q "Connection refused\|Cannot connect to redis"; then
        warn "Redis bağlantısı kurulamıyor, yeniden başlatılıyor..."
        systemctl start redis-server 2>/dev/null || \
        redis-server --daemonize yes --logfile /tmp/redis-nasri.log
        sleep 2
        return 0
    fi

    if echo "$error_msg" | grep -q "Permission denied"; then
        warn "İzin hatası — chmod düzeltmesi uygulanıyor"
        chmod +x "$NASRI_VENV/bin/"* 2>/dev/null
        chmod +x "$HOME/.local/bin/nasri" 2>/dev/null
        return 0
    fi

    return 1  # Kural eşleşmedi
}

# AI destekli onarım (Ollama hazırsa)
ai_heal() {
    local error_msg="$1"
    local context="$2"

    if ! curl -s --max-time 3 "http://localhost:11434/api/tags" &>/dev/null; then
        warn "Ollama henüz hazır değil, AI tanı atlanıyor"
        return 1
    fi

    log "Ollama'ya tanı isteği gönderiliyor..."

    local prompt="Sen bir Linux sistem yöneticisi ve Python uzmanısın. Aşağıdaki kurulum hatası için SADECE çalıştırılabilir bash komutları ver (açıklama yok, sadece komutlar). Her komut ayrı satırda olsun.

HATA: $error_msg

BAĞLAM: $context

ÖNEMLI: Sadece güvenli, geri alınabilir komutlar öner. rm -rf gibi tehlikeli komutlar önerme."

    local response
    response=$(curl -s --max-time 30 -X POST "http://localhost:11434/api/generate" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"$OLLAMA_MODEL\",\"prompt\":$(echo "$prompt" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),\"stream\":false}" \
        2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("response",""))' 2>/dev/null)

    if [ -z "$response" ]; then
        warn "AI yanıt vermedi"
        return 1
    fi

    log "AI önerisi alındı, uygulanıyor..."

    # Yanıttaki bash komutlarını çıkar ve çalıştır
    echo "$response" | grep -E "^(apt|pip|systemctl|mkdir|chmod|curl|git|redis|ollama|export|echo)" | while IFS= read -r cmd; do
        warn "Çalıştırılıyor: $cmd"
        eval "$cmd" 2>/dev/null && ok "Başarılı: $cmd" || warn "Başarısız: $cmd"
    done

    return 0
}

# Adım çalıştırıcı — hata olursa heal et ve tekrar dene
run_step() {
    local desc="$1"
    shift
    local output
    log "$desc"
    if output=$("$@" 2>&1); then
        ok "$desc"
        return 0
    fi

    err "$desc BAŞARISIZ"
    err "Hata: $output"

    # Önce kural tabanlı dene
    if rule_based_heal "$output"; then
        log "Onarım uygulandı, tekrar deneniyor..."
        if "$@" 2>/dev/null; then
            ok "$desc (onarım sonrası)"
            return 0
        fi
    fi

    # AI destekli dene
    if ai_heal "$output" "$desc"; then
        log "AI onarımı uygulandı, tekrar deneniyor..."
        if "$@" 2>/dev/null; then
            ok "$desc (AI onarımı sonrası)"
            return 0
        fi
    fi

    err "$desc kurtarılamadı. Log: $NASRI_LOG"
    return 1
}

# =============================================================================
# ADIM 1: SİSTEM ÖN GEREKSİNİMLERİ
# =============================================================================
step "1/7 — Sistem ön gereksinimleri kontrol ediliyor"

OS=$(uname -s)
if [ "$OS" = "Linux" ]; then
    if command_exists apt-get; then
        log "apt paket yöneticisi bulundu"

        PACKAGES_NEEDED=""
        command_exists git        || PACKAGES_NEEDED="$PACKAGES_NEEDED git"
        command_exists python3    || PACKAGES_NEEDED="$PACKAGES_NEEDED python3"
        python3 -m venv --help &>/dev/null || PACKAGES_NEEDED="$PACKAGES_NEEDED python3-venv"
        command_exists pip3       || PACKAGES_NEEDED="$PACKAGES_NEEDED python3-pip"
        command_exists curl       || PACKAGES_NEEDED="$PACKAGES_NEEDED curl"
        command_exists redis-server || PACKAGES_NEEDED="$PACKAGES_NEEDED redis-server"
        command_exists ss         || PACKAGES_NEEDED="$PACKAGES_NEEDED iproute2"

        if [ -n "$PACKAGES_NEEDED" ]; then
            log "Kurulacak paketler:$PACKAGES_NEEDED"
            run_step "apt güncelleniyor" apt-get update -qq
            run_step "Paketler kuruluyor" apt-get install -y $PACKAGES_NEEDED
        else
            ok "Tüm sistem paketleri mevcut"
        fi
    fi
elif [ "$OS" = "Darwin" ]; then
    command_exists brew || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    command_exists redis-server || brew install redis
fi

# =============================================================================
# ADIM 2: REDİS
# =============================================================================
step "2/7 — Redis kontrol ediliyor"

if redis-cli ping &>/dev/null; then
    ok "Redis zaten çalışıyor"
elif port_in_use 6379; then
    warn "Port 6379 kullanımda ama Redis ping yanıt vermiyor"
    warn "Muhtemelen başka bir uygulama portu tutuyor"
    warn "Devam ediliyor — Nasri farklı port kullanabilir"
else
    log "Redis başlatılıyor..."
    if command_exists systemctl; then
        run_step "Redis servisi başlatılıyor" systemctl enable --now redis-server
    else
        redis-server --daemonize yes --logfile /tmp/redis-nasri.log
    fi
    sleep 2
    if redis-cli ping &>/dev/null; then
        ok "Redis aktif"
    else
        warn "Redis başlatılamadı — Nasri hafıza modu ile çalışacak"
    fi
fi

# =============================================================================
# ADIM 3: OLLAMA
# =============================================================================
step "3/7 — Ollama kontrol ediliyor"

if command_exists ollama && curl -s --max-time 3 "http://localhost:11434/api/tags" &>/dev/null; then
    ok "Ollama zaten çalışıyor"
else
    if ! command_exists ollama; then
        log "Ollama kuruluyor..."
        run_step "Ollama indiriliyor ve kuruluyor" bash -c "curl -fsSL https://ollama.com/install.sh | sh"
    fi

    log "Ollama servisi başlatılıyor..."
    if command_exists systemctl; then
        systemctl enable --now ollama 2>/dev/null || true
    else
        ollama serve &>/dev/null &
    fi

    log "Ollama hazır olana bekleniyor (max 30s)..."
    for i in $(seq 1 30); do
        curl -s --max-time 2 "http://localhost:11434/api/tags" &>/dev/null && break
        sleep 1
    done

    if curl -s --max-time 3 "http://localhost:11434/api/tags" &>/dev/null; then
        ok "Ollama aktif"
    else
        warn "Ollama başlatılamadı — API devre dışı çalışacak"
    fi
fi

# Model kontrolü
if command_exists ollama && curl -s --max-time 3 "http://localhost:11434/api/tags" &>/dev/null; then
    if ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
        ok "Model $OLLAMA_MODEL mevcut"
    else
        log "Model indiriliyor: $OLLAMA_MODEL (bu biraz sürebilir)..."
        ollama pull "$OLLAMA_MODEL" && ok "Model hazır: $OLLAMA_MODEL" || warn "Model indirilemedi"
    fi
fi

# =============================================================================
# ADIM 4: REPO
# =============================================================================
step "4/7 — Nasri kaynak kodu"

if [ -d "$NASRI_SRC/.git" ]; then
    log "Mevcut kurulum güncelleniyor..."
    run_step "git pull" git -C "$NASRI_SRC" pull --ff-only origin main
else
    log "Repo klonlanıyor: $REPO_URL"
    run_step "git clone" git clone "$REPO_URL" "$NASRI_SRC"
fi
ok "Kaynak kod hazır: $NASRI_SRC"

# =============================================================================
# ADIM 5: PYTHON ORTAMI VE PAKETLER
# =============================================================================
step "5/7 — Python ortamı ve bağımlılıklar"

if [ ! -d "$NASRI_VENV" ]; then
    run_step "venv oluşturuluyor" python3 -m venv "$NASRI_VENV"
fi

run_step "pip güncelleniyor" "$NASRI_VENV/bin/python" -m pip install --upgrade pip --quiet
run_step "requirements.txt kuruluyor" "$NASRI_VENV/bin/python" -m pip install \
    -r "$NASRI_SRC/project/nasri-core/requirements.txt" --quiet
run_step "nasri-core kuruluyor" "$NASRI_VENV/bin/python" -m pip install \
    -e "$NASRI_SRC/project/nasri-core" --quiet

# Kurulumu doğrula
log "Kritik modüller doğrulanıyor..."
MISSING_MODS=""
for mod in uvicorn fastapi redis cryptography python_multipart; do
    "$NASRI_VENV/bin/python" -c "import $mod" 2>/dev/null || MISSING_MODS="$MISSING_MODS $mod"
done

if [ -n "$MISSING_MODS" ]; then
    warn "Eksik modüller:$MISSING_MODS — tek tek kuruluyor"
    for mod in $MISSING_MODS; do
        "$NASRI_VENV/bin/pip" install "$mod" --quiet && ok "$mod kuruldu"
    done
fi

ok "Python ortamı hazır"

# =============================================================================
# ADIM 6: YAPILANDIRMA (.env)
# =============================================================================
step "6/7 — Yapılandırma"

ENV_FILE="$NASRI_SRC/project/nasri-core/.env"
if [ ! -f "$ENV_FILE" ]; then
    cp "$NASRI_SRC/project/nasri-core/.env.example" "$ENV_FILE"
    log ".env dosyası oluşturuldu"
fi

# Port çakışması varsa otomatik çöz
API_PORT=$(find_free_port "$API_PORT")
if [ "$API_PORT" != "${NASRI_API_PORT:-8000}" ]; then
    warn "Port 8000 kullanımda, $API_PORT kullanılacak"
    sed -i "s/^NASRI_API_PORT=.*/NASRI_API_PORT=$API_PORT/" "$ENV_FILE" 2>/dev/null || \
        echo "NASRI_API_PORT=$API_PORT" >> "$ENV_FILE"
fi

# Redis bağlantısını .env'e yaz
if redis-cli ping &>/dev/null; then
    grep -q "^REDIS_HOST=" "$ENV_FILE" || echo "REDIS_HOST=localhost" >> "$ENV_FILE"
    grep -q "^REDIS_PORT=" "$ENV_FILE" || echo "REDIS_PORT=6379" >> "$ENV_FILE"
fi

ok "Yapılandırma hazır ($ENV_FILE)"

# =============================================================================
# ADIM 7: SERVİS KURULUMU VE BAŞLATMA
# =============================================================================
step "7/7 — Servis kurulumu"

# nasri komutunu PATH'e ekle
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/nasri" <<NASRI_CMD
#!/usr/bin/env bash
export NASRI_INSTALL_DIR="$NASRI_SRC"
export NASRI_DATA_DIR="$NASRI_DATA_DIR"
export NASRI_API_PORT="$API_PORT"
exec "$NASRI_VENV/bin/nasri" "\$@"
NASRI_CMD
chmod +x "$HOME/.local/bin/nasri"

# PATH kalıcı hale getir
export PATH="$HOME/.local/bin:$PATH"
for rc in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.zshrc"; do
    if [ -f "$rc" ] && ! grep -q '.local/bin' "$rc"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
    fi
done

# Systemd servisi kur
if command_exists systemctl && [ "$OS" = "Linux" ]; then
    NASRI_INSTALL_DIR="$NASRI_SRC" NASRI_DATA_DIR="$NASRI_DATA_DIR" \
    NASRI_API_PORT="$API_PORT" \
    "$NASRI_VENV/bin/nasri" install-service 2>/dev/null && ok "Systemd servisi kuruldu"

    systemctl start nasri.service 2>/dev/null || true
    sleep 3

    if systemctl is-active --quiet nasri.service; then
        ok "Nasri servisi çalışıyor"
    else
        warn "Servis başlatılamadı, loglar kontrol ediliyor..."
        LAST_ERR=$(journalctl -u nasri.service -n 5 --no-pager 2>/dev/null | tail -3)
        rule_based_heal "$LAST_ERR" || ai_heal "$LAST_ERR" "systemd servis başlatma"
        systemctl restart nasri.service 2>/dev/null || true
        sleep 5
    fi
elif [ "$OS" = "Darwin" ]; then
    "$NASRI_VENV/bin/nasri" install-service
fi

# =============================================================================
# SONUÇ RAPORU
# =============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║      Nasri Kurulumu Tamamlandı!          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

# Servis durumu
SVC_STATUS="bilinmiyor"
command_exists systemctl && SVC_STATUS=$(systemctl is-active nasri.service 2>/dev/null || echo "çalışmıyor")
echo -e "  Servis:    ${CYAN}$SVC_STATUS${NC}"
echo -e "  API Port:  ${CYAN}$API_PORT${NC}"
echo -e "  Veri:      ${CYAN}$NASRI_DATA_DIR${NC}"
echo -e "  Log:       ${CYAN}$NASRI_LOG${NC}"
echo ""
echo -e "  ${YELLOW}Kullanım:${NC}"
echo -e "    ${GREEN}nasri /status${NC}   — durum kontrolu"
echo -e "    ${GREEN}nasri /version${NC}  — surum bilgisi"
echo -e "    ${GREEN}nasri /chat${NC}     — sohbet baslat"
echo -e "    ${GREEN}nasri start${NC}     — servisi on planda calistir"
echo ""

if ! command_exists nasri; then
    echo -e "  ${YELLOW}PATH güncellemesi için:${NC}"
    echo -e "    ${GREEN}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
    echo -e "  veya yeni terminal aç."
    echo ""
fi

# Son durum kontrolü
"$HOME/.local/bin/nasri" /status 2>/dev/null || \
    "$NASRI_VENV/bin/nasri" /status 2>/dev/null || true
