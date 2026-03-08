#!/usr/bin/env bash
# Nasri GitHub Labels, Milestones ve Project kurulum scripti
# Gereksinim: gh CLI kurulu ve `gh auth login` yapilmis olmali
# Kullanim: bash scripts/setup-github.sh

set -euo pipefail

REPO="feyzeddin/nasri-local-ai"

echo "=== REPO: $REPO ==="

# ---------------------------------------------------------------------------
# MEVCUT DEFAULT LABEL'LARI SIL (github'un otomatik olusturduklari)
# ---------------------------------------------------------------------------
echo ""
echo "[1/3] Varsayilan label'lar siliniyor..."
DEFAULT_LABELS=("bug" "documentation" "duplicate" "enhancement" "good first issue" "help wanted" "invalid" "question" "wontfix")
for label in "${DEFAULT_LABELS[@]}"; do
  gh label delete "$label" --repo "$REPO" --yes 2>/dev/null || true
done

# ---------------------------------------------------------------------------
# LABEL'LAR
# ---------------------------------------------------------------------------
echo ""
echo "[2/3] Label'lar olusturuluyor..."

# --- Tip ---
gh label create "tip:feat"   --repo "$REPO" --color "0075ca" --description "Yeni ozellik" --force
gh label create "tip:bug"    --repo "$REPO" --color "d73a4a" --description "Hata bildirimi" --force
gh label create "tip:chore"  --repo "$REPO" --color "e4e669" --description "Teknik borc / altyapi" --force
gh label create "tip:docs"   --repo "$REPO" --color "0075ca" --description "Dokumantasyon" --force
gh label create "tip:test"   --repo "$REPO" --color "cfd3d7" --description "Test yazimi" --force

# --- Faz ---
gh label create "faz:f0"  --repo "$REPO" --color "bfd4f2" --description "F0 - Iskelet" --force
gh label create "faz:f1"  --repo "$REPO" --color "bfd4f2" --description "F1 - FastAPI temel" --force
gh label create "faz:f2"  --repo "$REPO" --color "bfd4f2" --description "F2 - Ayarlar / Config" --force
gh label create "faz:f3"  --repo "$REPO" --color "bfd4f2" --description "F3 - CLI" --force
gh label create "faz:f4"  --repo "$REPO" --color "bfd4f2" --description "F4 - Background Service" --force
gh label create "faz:f5"  --repo "$REPO" --color "bfd4f2" --description "F5 - Auto-updater" --force
gh label create "faz:f6"  --repo "$REPO" --color "bfd4f2" --description "F6 - Platform servis kurulumu" --force
gh label create "faz:f7"  --repo "$REPO" --color "bfd4f2" --description "F7 - Web UI iskelet" --force
gh label create "faz:f8"  --repo "$REPO" --color "bfd4f2" --description "F8 - CI / CD" --force
gh label create "faz:f9"  --repo "$REPO" --color "5319e7" --description "F9 - LLM Chat API" --force
gh label create "faz:f10" --repo "$REPO" --color "5319e7" --description "F10 - Redis Session" --force
gh label create "faz:f11" --repo "$REPO" --color "5319e7" --description "F11 - nasri-ui Chat" --force
gh label create "faz:f12" --repo "$REPO" --color "5319e7" --description "F12 - ..." --force

# --- Oncelik ---
gh label create "oncelik:yuksek" --repo "$REPO" --color "e99695" --description "Acil / kritik" --force
gh label create "oncelik:orta"   --repo "$REPO" --color "f9d0c4" --description "Normal oncelik" --force
gh label create "oncelik:dusuk"  --repo "$REPO" --color "fef2c0" --description "Gerekli ama bekleyebilir" --force

# --- Durum ---
gh label create "bloklu"       --repo "$REPO" --color "9b59b6" --description "Baska issue/PR bekliyor" --force
gh label create "inceleniyor"  --repo "$REPO" --color "f39c12" --description "Takim icinde tartisiliyor" --force

echo "Label'lar hazir."

# ---------------------------------------------------------------------------
# MILESTONE'LAR
# ---------------------------------------------------------------------------
echo ""
echo "[3/3] Milestone'lar olusturuluyor..."

gh api repos/$REPO/milestones \
  --method POST \
  --field title="F9 — LLM Chat API" \
  --field description="Ollama entegrasyonu, POST /chat endpoint, StreamingResponse" \
  --field state="open" 2>/dev/null || echo "  F9 zaten mevcut, atlaniyor."

gh api repos/$REPO/milestones \
  --method POST \
  --field title="F10 — Redis Oturum" \
  --field description="Konusma gecmisi Redis'te saklanir, session yonetimi" \
  --field state="open" 2>/dev/null || echo "  F10 zaten mevcut, atlaniyor."

gh api repos/$REPO/milestones \
  --method POST \
  --field title="F11 — nasri-ui Chat" \
  --field description="Web arayuzu chat sayfasi, SSE/WebSocket streaming" \
  --field state="open" 2>/dev/null || echo "  F11 zaten mevcut, atlaniyor."

gh api repos/$REPO/milestones \
  --method POST \
  --field title="F12 — Auth & Guvenik" \
  --field description="API key, lokal kimlik dogrulama, guvenli config" \
  --field state="open" 2>/dev/null || echo "  F12 zaten mevcut, atlaniyor."

echo "Milestone'lar hazir."

# ---------------------------------------------------------------------------
# GITHUB PROJECT (kanban)
# ---------------------------------------------------------------------------
echo ""
echo "GitHub Project kanban tahtasi icin:"
echo "  https://github.com/orgs/feyzeddin/projects adresinden veya"
echo "  https://github.com/feyzeddin/nasri-local-ai/projects altindan"
echo "  'New project → Board' ile olusturun."
echo "  Sutunlar: Backlog | In Progress | In Review | Done"
echo ""
echo "=== Kurulum tamamlandi ==="
