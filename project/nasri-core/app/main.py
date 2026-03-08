from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.core.security import rate_limit, verify_api_key
from app.core.settings import get_settings


def _create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(title="nasri-core", version="0.1.0")

    # F12.2 — CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # F12.1 + F12.3 — Auth + Rate limit tüm /chat rotalarına uygulanır
    application.include_router(
        chat_router,
        dependencies=[Depends(verify_api_key), Depends(rate_limit)],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/config")
    def config() -> dict[str, str | int]:
        s = get_settings()
        return {
            "redis_host": s.redis_host,
            "redis_port": s.redis_port,
            "ollama_url": s.ollama_url,
            "model_name": s.model_name,
        }

    return application


app = _create_app()
