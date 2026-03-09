# nasri-core

FastAPI + Redis + Ollama entegrasyonu için backend servis alanı.

## Çalıştırma

1. `copy .env.example .env`
2. `pip install -r requirements.txt`
3. `uvicorn app.main:app --reload`

## Docker ile

- `docker compose up -d` (nasri-core dizininde)

## Sağlık Endpointleri

- `GET /health` temel canlılık kontrolü
- `GET /health/ready` Redis + Ollama bağımlılık hazır olma kontrolü

## Konuşma (STT)

- `POST /speech/transcribe` (multipart form-data, `audio` alanı)
- Backend: `whisper.cpp`
- `POST /speech/synthesize` (JSON: `{ "text": "..." }`)
- Backend: `piper`

## Çok Kullanıcılı Profil (Identity)

- `POST /identity/enroll`
- `POST /identity/verify`
- `GET /identity/profiles`
- `DELETE /identity/profiles/{profile_id}`

## RAG

- `POST /rag/index` (doküman/chunk indexleme)
- `GET /rag/query?q=...&top_k=...` (semantic arama)
- Varsayılan embedding modeli: `nomic-embed-text` (Ollama)

## Memory Manager

- `POST /memory/store` (profil bazlı uzun vadeli bellek yazma)
- `GET /memory/recall?profile_id=...&q=...` (semantik bellek geri çağırma)

## Planner (ReAct)

- `POST /planner/run` (goal + profile_id ile ReAct tarzı adım planı üretir)

## Model Router (3 katman)

- `POST /model-router/chat`
- Katman sırası: `local -> free -> paid` (env ile değiştirilebilir)
- Bir katman hata verirse bir sonraki katmana otomatik fallback yapılır

## External AI (Groq, Gemini, OpenRouter)

- `POST /external-ai/chat`
- Provider bazlı rate-limit (`*_RPM`) uygulanır
- İstek metni isteğe bağlı anonimleştirilir (`EXTERNAL_AI_ANONYMIZE_ENABLED=1`)
- Redis üzerinde günlük token/maliyet takibi tutulur (`external_ai:cost:*` anahtarları)

## LAN Tarama ve Cihaz Keşfi

- `POST /network/discover`
- `nmap -sn` ile ağdaki aktif cihazlar bulunur
- Opsiyonel `mDNS` keşfi ile hostname zenginleştirmesi yapılır
- Cihazlar için basit sahiplik tahmini (`likely_owned`, `possible_owned`, `unknown`) üretilir

## SSH Uzak Cihaz Yönetimi

- `POST /ssh/profiles` (profil + güvenli credential saklama)
- `GET /ssh/profiles/{profile_name}`
- `DELETE /ssh/profiles/{profile_name}`
- `POST /ssh/exec` (uzak komut çalıştırma)
- `POST /ssh/upload` ve `POST /ssh/download` (SFTP dosya transferi)

## Home Assistant + MQTT Köprüsü

- `POST /home-automation/command`
- Doğal dil komutlarını temel aksiyonlara çevirir (`turn_on`, `turn_off`, `set_temperature`)
- `mode=auto` ise önce Home Assistant, başarısızsa MQTT fallback uygulanır

## Sistem Bakım Otomasyonu

- `GET /maintenance/status`
- `POST /maintenance/run`
- Disk kullanım raporu, log temizliği ve opsiyonel sistem güncellemesi adımlarını içerir
- Arka planda periyodik worker ile due olduğunda otomatik tetiklenir

## Web Araştırma Ajanı

- `POST /research/query`
- SearXNG ile arama yapar (`RESEARCH_SEARXNG_URL`)
- Güvenilir domain filtresi uygular (`RESEARCH_ALLOWED_DOMAINS`)
- Sayfa içeriğini özetler ve raporu yerel dosyaya kaydeder (`RESEARCH_SAVE_DIR`)

## Anomaly Detector

- `GET /anomaly/status`
- `POST /anomaly/ingest`
- `GET /anomaly/alerts`
- Ağ trafiği ve dosya erişimi olayları için eşik tabanlı anomali tespiti ve uyarı üretimi

## Backup Manager

- `POST /backup/run`
- `GET /backup/history`
- Kaynak yolları arşivlenir, opsiyonel AES ile şifrelenir ve yerel backup dizinine yazılır
- Retention sayısına göre eski yedekler otomatik temizlenir

## Driver Manager

- `GET /driver/scan`
- `POST /driver/install`
- Windows/Linux için sürücü tarama ve kontrollü kurulum akışı sağlar

## Code Generator

- `POST /codegen/generate`
- Gereksinim + dil/framework seçimine göre başlangıç proje iskeleti üretir
- Üretilen dosyalar `CODEGEN_OUTPUT_ROOT` altında saklanır

## Zigbee Bridge

- `GET /zigbee/status`
- `GET /zigbee/devices`
- `POST /zigbee/permit-join`
- `POST /zigbee/action`
- zigbee2mqtt HTTP API üzerinden cihaz eşleştirme ve temel komut akışı sağlar

## Matter/Thread Bridge

- `GET /matter/status`
- `GET /matter/devices`
- `POST /matter/pair`
- `POST /matter/action`
- Matter controller API üzerinden Thread cihaz keşfi, eşleştirme ve komut akışı sağlar

## Beta Program

- `POST /beta-program/candidates` (admin/operator)
- `GET /beta-program/candidates` (admin/operator/viewer)
- `POST /beta-program/feedback` (admin/operator/viewer)
- `GET /beta-program/feedback?limit=...`
- NDA kabul işareti ve geri bildirim kayıtları Redis üzerinde tutulur

## Pricing + Early Access

- `GET /pricing/plans`
- `POST /pricing/quote`
- `GET /pricing/promo/{code}`
- Freemium / Pro / Enterprise planları, yıllık indirim ve erken erişim kodu indirimi hesaplanır

## Fine-Tuning Pipeline (QLoRA)

- `POST /fine-tuning/datasets`
- `GET /fine-tuning/datasets`
- `POST /fine-tuning/jobs/start`
- `GET /fine-tuning/jobs/{job_id}`
- `GET /fine-tuning/jobs?limit=...`
- Dry-run modunda adapter metadata üretilir; gerçek eğitim için `FINE_TUNING_ALLOW_EXECUTE=1` gerekir

## Otonom Ajan Ağı

- `POST /agent-network/run`
- `GET /agent-network/runs/{run_id}`
- `GET /agent-network/runs?limit=...`
- `planner`, `memory`, `risk` alt-ajanları paralel veya sıralı çalıştırılır

## International + GDPR

- `POST /international/locale`
- `GET /international/locale/{profile_id}`
- `POST /international/gdpr/export`
- `POST /international/gdpr/erase`
- Locale tercihleri (`tr/en/de`) ve profil verileri için export/erase akışı sağlar

## Proaktif Öneri Motoru

- `GET /suggestions/proactive?profile_id=...`
- Profil bazlı bellek sinyallerinden ve zaman bilgisinden öneriler üretir

## Self-Heal Döngüsü

- `GET /self-heal/status`
- `POST /self-heal/run?force=true|false`
- Hata tespiti (maintenance/anomaly) sonrası otomatik bakım ve yedek aksiyonları çalıştırır

## Federation Base

- `POST /federation/peers` (peer kayıt/güncelleme)
- `GET /federation/peers` (kayıtlı peer listesi)
- `DELETE /federation/peers/{peer_id}` (peer silme)
- `POST /federation/dispatch` (uzak peer endpoint'ine payload gönderme)
- `POST /federation/inbox` (X-Federation-Token ile korumalı alıcı endpoint)

## Test Runner

- `POST /test-runner/run` (pytest çalıştırır, çıktı + süre + kod döner)
- `GET /test-runner/status` (son test koşumunu getirir)
- `GET /test-runner/history?limit=10` (son koşum geçmişi)

## Dependency Auditor

- `POST /dependency-auditor/scan`
- `GET /dependency-auditor/status`
- Python tarafında `pip list --outdated`, UI tarafında `npm audit --json` çıktıları toplanır
