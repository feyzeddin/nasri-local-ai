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
