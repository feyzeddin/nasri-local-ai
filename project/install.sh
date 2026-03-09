#!/usr/bin/env bash
set -euo pipefail

NASRI_HOME="${NASRI_HOME:-$HOME/.nasri}"
NASRI_SRC="$NASRI_HOME/src"
NASRI_VENV="$NASRI_HOME/venv"
NASRI_DATA_DIR="$NASRI_HOME/data"
REPO_URL="${NASRI_REPO_URL:-https://github.com/feyzeddin/nasri-local-ai.git}"

mkdir -p "$NASRI_HOME"
mkdir -p "$NASRI_DATA_DIR"

if [ -d "$NASRI_SRC/.git" ]; then
  git -C "$NASRI_SRC" fetch origin main
  git -C "$NASRI_SRC" pull --ff-only origin main
else
  git clone "$REPO_URL" "$NASRI_SRC"
fi

if [ ! -d "$NASRI_VENV" ]; then
  python3 -m venv "$NASRI_VENV"
fi

"$NASRI_VENV/bin/python" -m pip install --upgrade pip
"$NASRI_VENV/bin/python" -m pip install -r "$NASRI_SRC/project/nasri-core/requirements.txt"
"$NASRI_VENV/bin/python" -m pip install -e "$NASRI_SRC/project/nasri-core"

mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/nasri" <<EOF
#!/usr/bin/env bash
export NASRI_INSTALL_DIR="$NASRI_SRC"
export NASRI_DATA_DIR="$NASRI_DATA_DIR"
exec "$NASRI_VENV/bin/nasri" "\$@"
EOF
chmod +x "$HOME/.local/bin/nasri"

# PATH'e ekle (oturumda hemen kullanilabilsin)
export PATH="$HOME/.local/bin:$PATH"

# Shell rc dosyasina da ekle (kalici)
for rc in "$HOME/.bashrc" "$HOME/.profile"; do
  if [ -f "$rc" ] && ! grep -q '.local/bin' "$rc"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
  fi
done

export NASRI_INSTALL_DIR="$NASRI_SRC"
export NASRI_DATA_DIR="$NASRI_DATA_DIR"

case "$(uname -s)" in
  Linux*)
    if command -v sudo >/dev/null 2>&1; then
      sudo env "NASRI_INSTALL_DIR=$NASRI_SRC" "NASRI_DATA_DIR=$NASRI_DATA_DIR" "PATH=$HOME/.local/bin:$PATH" "$NASRI_VENV/bin/nasri" install-service
    else
      # sudo yoksa (zaten root) dogrudan calistir
      NASRI_INSTALL_DIR="$NASRI_SRC" NASRI_DATA_DIR="$NASRI_DATA_DIR" "$NASRI_VENV/bin/nasri" install-service
    fi
    ;;
  Darwin*)
    "$NASRI_VENV/bin/nasri" install-service
    ;;
  *)
    echo "Bu script sadece Linux/macOS icin. Windows icin install.ps1 kullanin."
    exit 1
    ;;
esac

echo ""
echo "============================================"
echo "  Kurulum tamamlandi!"
echo "============================================"
echo ""
echo "Kullanim:"
echo "  nasri /status   — durum kontrolu"
echo "  nasri /version  — surum bilgisi"
echo "  nasri /help     — komut listesi"
echo "  nasri start     — servisi on planda baslat"
echo ""
echo "PATH guncellendi. Yeni terminalde veya su komutla aktif edilir:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
