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
