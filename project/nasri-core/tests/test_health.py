from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_ok(monkeypatch) -> None:
    async def _ok() -> dict:
        return {
            "status": "ok",
            "checks": {
                "redis": {"ok": True, "detail": "ok"},
                "ollama": {"ok": True, "detail": "ok"},
            },
        }

    monkeypatch.setattr(main_module, "build_readiness", _ok)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_ready_degraded_returns_503(monkeypatch) -> None:
    async def _degraded() -> dict:
        return {
            "status": "degraded",
            "checks": {
                "redis": {"ok": False, "detail": "error:connection"},
                "ollama": {"ok": True, "detail": "ok"},
            },
        }

    monkeypatch.setattr(main_module, "build_readiness", _degraded)
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["status"] == "degraded"
    assert body["detail"]["checks"]["redis"]["ok"] is False
