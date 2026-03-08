# Nasri Monorepo

Bu repo 3 ana paketten oluşur:

- `nasri-core`: FastAPI + Redis + LLM orkestrasyonu (backend + `nasri` CLI/service)
- `nasri-ui`: Web arayüzü
- `nasri-modules`: Ortak modüller / domain package'ları

## Tek Komut Kurulum

- Linux/macOS:
  - `bash install.sh`
- Windows (PowerShell):
  - `powershell -ExecutionPolicy Bypass -File .\install.ps1`

Kurulum sonrası servis otomatik kurulur ve açılışta yeniden ayağa kalkar.

## Nasri Komutları

- `nasri /status`
- `nasri /version`
- `nasri /help`

`/status` çıktısı:

- `Selamunaleyküm ben Nasrî`

## Klasör Yapısı

- `nasri-core/`
- `nasri-ui/`
- `nasri-modules/`
- `.github/workflows/`
- `docs/`

## Core Hızlı Başlangıç

1. Python ortamı oluştur:
   - `python -m venv .venv`
   - Windows: `.venv\Scripts\activate`
2. Bağımlılıkları kur:
   - `pip install -r nasri-core/requirements.txt`
3. Ortam değişkenlerini kopyala:
   - `copy nasri-core\.env.example nasri-core\.env`
4. API'yi çalıştır:
   - `uvicorn nasri-core.app.main:app --reload`

## UI Hızlı Başlangıç

1. UI bağımlılıklarını kur:
   - `cd nasri-ui && npm install`
2. UI geliştirme sunucusu:
   - `npm run dev`

## Branch Stratejisi (Özet)

- `main`: production'a çıkan stabil kod
- `develop`: bir sonraki release'in entegrasyon branşı
- `feature/<scope>-<kisa-aciklama>`: yeni geliştirmeler
- `fix/<scope>-<kisa-aciklama>`: develop bazlı bugfix
- `release/<version>`: release hazırlığı
- `hotfix/<scope>-<kisa-aciklama>`: main bazlı acil düzeltme

Detay: `docs/BRANCH_STRATEGY.md`
GitHub kurulum adımları: `docs/GITHUB_SETUP.md`
Nasri kurulum/servis: `docs/NASRI_INSTALL_AND_SERVICE.md`
CI/CD akışı: `docs/CICD_PIPELINE.md`

## GitHub Koruma Kuralları

- `main` ve `develop` için branch protection açık olmalı
- En az 1 PR review zorunlu
- CI (`core-checks`, `ui-checks`) başarı zorunlu
- Doğrudan push kapalı
- CD için `staging` ve `production` environment onayları aktif olmalı

## Commit Konvansiyonu

Conventional Commits önerilir:

- `feat(core): redis queue worker eklendi`
- `fix(ui): login redirect düzeltildi`
- `chore(modules): shared dto güncellendi`
