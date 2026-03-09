# Nasri Kurulum ve Servis

## Hedef

- `nasri` tek komutla kurulabilir.
- Kurulumdan sonra arkaplanda servis olarak calisir.
- Yeniden baslatma/kapanma sonrasi otomatik ayağa kalkar.
- Gunde bir kez repo versiyon kontrolu yapar ve fark varsa gunceller.

## Komutlar

- `nasri /status`
- `nasri /version`
- `nasri /help`

`/status` ciktisi ilk satirda su metni verir:

- `Selamunaleyküm ben Nasrî`

## One-command kurulum

- Linux/macOS:
  - `bash install.sh`
- Windows:
  - `powershell -ExecutionPolicy Bypass -File .\install.ps1`

## Servis Yonetimi

- Linux: `systemd` (`nasri.service`)
- macOS: `launchd` (`com.nasri.service`)
- Windows: `Task Scheduler` (`NasriService`)

## Auto Update Akisi

Servis 30 saniyede bir dongu calistirir, fakat update kontrolunu 24 saatte bir yapar.

- `git fetch origin main`
- `HEAD` ve `origin/main` karsilastir
- fark varsa `git pull --ff-only origin main`
- `project/UPDATE_MANIFEST.json` okunur
- Python bagimliliklari (`requirements.txt`) kurulup editable paketler guncellenir
- `.env.example` icindeki yeni anahtarlar `.env` dosyasina eklenir

Durum bilgileri `NASRI_DATA_DIR/state.json` icine yazilir.

## Telegram Kurulumu (v0.2.0)

- `nasri telegram-setup`
- Komut sirasinda `TELEGRAM_BOT_TOKEN` istenir.
- Opsiyonel public webhook URL verilirse Telegram `setWebhook` otomatik cagirilir.
- Girilen degerler `project/nasri-core/.env` dosyasina yazilir.
