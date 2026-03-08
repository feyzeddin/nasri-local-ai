from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.core.settings import get_settings


app = FastAPI(title="nasri-core", version="0.1.0")
app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def config() -> dict[str, str | int]:
    settings = get_settings()
    return {
        "redis_host": settings.redis_host,
        "redis_port": settings.redis_port,
        "ollama_url": settings.ollama_url,
        "model_name": settings.model_name,
    }
