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
