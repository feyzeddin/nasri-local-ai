from functools import lru_cache
import json
import os

from dotenv import load_dotenv


load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model_name = os.getenv("MODEL_NAME", "llama3")
        # Konuşma geçmişi: kaç mesaj çifti (kullanıcı+asistan) saklanacak
        self.max_history_pairs = int(os.getenv("MAX_HISTORY_PAIRS", "10"))
        # Redis'te oturum key'inin geçerlilik süresi (saniye), varsayılan 1 saat
        self.session_ttl_seconds = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
        # Nasri'nin kişiliğini ve görev kapsamını tanımlayan sistem mesajı
        self.system_prompt: str | None = os.getenv("NASRI_SYSTEM_PROMPT") or None
        # F12.1 — API Key auth (boşsa auth devre dışı)
        self.api_key: str | None = os.getenv("NASRI_API_KEY") or None
        # F12.2 — CORS izin verilen originler (virgülle ayrılmış)
        self.cors_origins: list[str] = [
            o.strip()
            for o in os.getenv("NASRI_CORS_ORIGINS", "http://localhost:5173").split(",")
            if o.strip()
        ]
        # F12.3 — Rate limit: dakikada maksimum istek sayısı (per-IP)
        self.rate_limit_rpm: int = int(os.getenv("NASRI_RATE_LIMIT_RPM", "60"))
        # F1.07 — RBAC özelliği (0/1)
        self.rbac_enabled: bool = os.getenv("NASRI_RBAC_ENABLED", "0") in {
            "1",
            "true",
            "True",
        }
        # F1.07 — Auth oturum TTL
        self.auth_session_ttl_seconds: int = int(
            os.getenv("AUTH_SESSION_TTL_SECONDS", "28800")
        )
        # F1.07 — Kullanıcı tanımları (JSON: {"user":{"password":"...","role":"..."}})
        raw_users = os.getenv("NASRI_USERS_JSON")
        if raw_users:
            try:
                self.users: dict[str, dict[str, str]] = json.loads(raw_users)
            except json.JSONDecodeError:
                self.users = {}
        else:
            self.users = {
                "admin": {"password": "admin", "role": "admin"},
                "operator": {"password": "operator", "role": "operator"},
                "viewer": {"password": "viewer", "role": "viewer"},
            }


@lru_cache
def get_settings() -> Settings:
    return Settings()
