from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.files import router as files_router
from app.api.onboarding import router as onboarding_router
from app.api.speech import router as speech_router
from app.api.vault import router as vault_router
from app.api.identity import router as identity_router
from app.api.rag import router as rag_router
from app.api.memory import router as memory_router
from app.api.planner import router as planner_router
from app.api.model_router import router as model_router_router
from app.api.external_ai import router as external_ai_router
from app.core.health import build_readiness
from app.core.security import AuthSession, rate_limit, require_roles, verify_api_key
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
    application.include_router(
        speech_router,
        dependencies=[Depends(verify_api_key), Depends(rate_limit)],
    )
    application.include_router(auth_router)
    application.include_router(files_router)
    application.include_router(onboarding_router)
    application.include_router(vault_router)
    application.include_router(identity_router)
    application.include_router(rag_router)
    application.include_router(memory_router)
    application.include_router(planner_router)
    application.include_router(model_router_router)
    application.include_router(external_ai_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready")
    async def health_ready() -> dict:
        result = await build_readiness()
        if result["status"] != "ok":
            raise HTTPException(status_code=503, detail=result)
        return result

    @application.get("/config")
    def config(
        _session: AuthSession = Depends(require_roles("admin")),
    ) -> dict[str, str | int]:
        s = get_settings()
        return {
            "redis_host": s.redis_host,
            "redis_port": s.redis_port,
            "ollama_url": s.ollama_url,
            "model_name": s.model_name,
        }

    return application


app = _create_app()
