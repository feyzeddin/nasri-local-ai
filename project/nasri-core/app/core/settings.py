from functools import lru_cache
import hashlib
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
        # F1.11 — Dosya yönetimi güvenli kök dizin
        self.files_root: str = os.getenv("NASRI_FILES_ROOT", os.getcwd())
        self.files_max_results: int = int(os.getenv("NASRI_FILES_MAX_RESULTS", "200"))
        # F1.04 — Whisper.cpp STT
        self.whisper_cpp_binary: str = os.getenv("WHISPER_CPP_BINARY", "").strip()
        self.whisper_cpp_model: str = os.getenv("WHISPER_CPP_MODEL", "").strip()
        self.whisper_cpp_language: str = os.getenv("WHISPER_CPP_LANGUAGE", "tr").strip()
        self.whisper_cpp_timeout_seconds: int = int(
            os.getenv("WHISPER_CPP_TIMEOUT_SECONDS", "180")
        )
        # F1.05 — Piper TTS
        self.piper_binary: str = os.getenv("PIPER_BINARY", "").strip()
        self.piper_model: str = os.getenv("PIPER_MODEL", "").strip()
        self.piper_output_sample_rate: int = int(
            os.getenv("PIPER_OUTPUT_SAMPLE_RATE", "22050")
        )
        self.piper_timeout_seconds: int = int(
            os.getenv("PIPER_TIMEOUT_SECONDS", "120")
        )
        # F1.06 — Credential Vault (AES-256)
        self.vault_master_key: str = os.getenv("NASRI_VAULT_MASTER_KEY", "").strip()
        self.vault_key_id: str = os.getenv("NASRI_VAULT_KEY_ID", "v1").strip()
        # F1.08 — Cihaz kimliği + biyometrik eşleştirme temeli
        self.device_fingerprint_salt: str = os.getenv(
            "NASRI_DEVICE_FINGERPRINT_SALT", "nasri-device-salt"
        ).strip()
        self.biometric_salt: str = os.getenv(
            "NASRI_BIOMETRIC_SALT", "nasri-biometric-salt"
        ).strip()
        # F2.01 — RAG (ChromaDB + nomic-embed-text)
        self.rag_collection_name: str = os.getenv("RAG_COLLECTION_NAME", "nasri_docs")
        self.rag_persist_dir: str = os.getenv("RAG_PERSIST_DIR", ".nasri-rag")
        self.rag_embedding_model: str = os.getenv(
            "RAG_EMBEDDING_MODEL", "nomic-embed-text"
        )
        self.rag_default_top_k: int = int(os.getenv("RAG_DEFAULT_TOP_K", "5"))
        # F2.02 — Long-term Memory Manager
        self.memory_collection_name: str = os.getenv(
            "MEMORY_COLLECTION_NAME", "nasri_memory"
        )
        self.memory_default_top_k: int = int(os.getenv("MEMORY_DEFAULT_TOP_K", "5"))
        # F2.03 — Planner (ReAct)
        self.planner_max_steps: int = int(os.getenv("PLANNER_MAX_STEPS", "6"))
        # F2.04 — Model Router (local -> free -> paid)
        self.model_router_tier_order: str = os.getenv(
            "MODEL_ROUTER_TIER_ORDER", "local,free,paid"
        )
        self.model_router_free_enabled: bool = os.getenv(
            "MODEL_ROUTER_FREE_ENABLED", "1"
        ) in {"1", "true", "True"}
        self.model_router_free_api_url: str = os.getenv(
            "MODEL_ROUTER_FREE_API_URL", ""
        ).strip()
        self.model_router_free_api_key: str = os.getenv(
            "MODEL_ROUTER_FREE_API_KEY", ""
        ).strip()
        self.model_router_free_model: str = os.getenv(
            "MODEL_ROUTER_FREE_MODEL", ""
        ).strip()
        self.model_router_paid_enabled: bool = os.getenv(
            "MODEL_ROUTER_PAID_ENABLED", "0"
        ) in {"1", "true", "True"}
        self.model_router_paid_api_url: str = os.getenv(
            "MODEL_ROUTER_PAID_API_URL", ""
        ).strip()
        self.model_router_paid_api_key: str = os.getenv(
            "MODEL_ROUTER_PAID_API_KEY", ""
        ).strip()
        self.model_router_paid_model: str = os.getenv(
            "MODEL_ROUTER_PAID_MODEL", ""
        ).strip()
        self.model_router_free_provider: str = os.getenv(
            "MODEL_ROUTER_FREE_PROVIDER", "groq"
        ).strip()
        self.model_router_paid_provider: str = os.getenv(
            "MODEL_ROUTER_PAID_PROVIDER", "openrouter"
        ).strip()
        # F2.05 — Dış AI API entegrasyonu
        self.external_ai_anonymize_enabled: bool = os.getenv(
            "EXTERNAL_AI_ANONYMIZE_ENABLED", "1"
        ) in {"1", "true", "True"}

        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "").strip()
        self.groq_api_url: str = os.getenv(
            "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"
        ).strip()
        self.groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
        self.groq_rpm: int = int(os.getenv("GROQ_RPM", "60"))
        self.groq_cost_input_per_1k: float = float(
            os.getenv("GROQ_COST_INPUT_PER_1K", "0")
        )
        self.groq_cost_output_per_1k: float = float(
            os.getenv("GROQ_COST_OUTPUT_PER_1K", "0")
        )

        self.openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.openrouter_api_url: str = os.getenv(
            "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
        ).strip()
        self.openrouter_model: str = os.getenv(
            "OPENROUTER_MODEL", "openai/gpt-4o-mini"
        ).strip()
        self.openrouter_rpm: int = int(os.getenv("OPENROUTER_RPM", "30"))
        self.openrouter_cost_input_per_1k: float = float(
            os.getenv("OPENROUTER_COST_INPUT_PER_1K", "0")
        )
        self.openrouter_cost_output_per_1k: float = float(
            os.getenv("OPENROUTER_COST_OUTPUT_PER_1K", "0")
        )

        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_api_url: str = os.getenv(
            "GEMINI_API_URL",
            "https://generativelanguage.googleapis.com/v1beta/models",
        ).strip()
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
        self.gemini_rpm: int = int(os.getenv("GEMINI_RPM", "30"))
        self.gemini_cost_input_per_1k: float = float(
            os.getenv("GEMINI_COST_INPUT_PER_1K", "0")
        )
        self.gemini_cost_output_per_1k: float = float(
            os.getenv("GEMINI_COST_OUTPUT_PER_1K", "0")
        )
        # F2.06 — LAN tarama + mDNS keşif
        self.lan_scan_default_cidr: str = os.getenv(
            "LAN_SCAN_DEFAULT_CIDR", "192.168.1.0/24"
        ).strip()
        self.lan_scan_timeout_seconds: int = int(
            os.getenv("LAN_SCAN_TIMEOUT_SECONDS", "30")
        )
        self.lan_scan_mdns_enabled: bool = os.getenv(
            "LAN_SCAN_MDNS_ENABLED", "1"
        ) in {"1", "true", "True"}
        # F2.07 — SSH remote management
        self.ssh_connect_timeout_seconds: int = int(
            os.getenv("SSH_CONNECT_TIMEOUT_SECONDS", "15")
        )
        # F2.08 — Home Assistant + MQTT bridge
        self.home_assistant_enabled: bool = os.getenv(
            "HOME_ASSISTANT_ENABLED", "0"
        ) in {"1", "true", "True"}
        self.home_assistant_url: str = os.getenv(
            "HOME_ASSISTANT_URL", "http://localhost:8123"
        ).strip()
        self.home_assistant_token: str = os.getenv("HOME_ASSISTANT_TOKEN", "").strip()
        self.home_assistant_default_area: str = os.getenv(
            "HOME_ASSISTANT_DEFAULT_AREA", "salon"
        ).strip()
        self.mqtt_enabled: bool = os.getenv("MQTT_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        self.mqtt_host: str = os.getenv("MQTT_HOST", "localhost").strip()
        self.mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
        self.mqtt_username: str = os.getenv("MQTT_USERNAME", "").strip()
        self.mqtt_password: str = os.getenv("MQTT_PASSWORD", "").strip()
        self.mqtt_topic_prefix: str = os.getenv("MQTT_TOPIC_PREFIX", "nasri").strip()
        # F2.09 — Sistem bakım otomasyonu
        self.maintenance_enabled: bool = os.getenv("MAINTENANCE_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        self.maintenance_interval_hours: int = int(
            os.getenv("MAINTENANCE_INTERVAL_HOURS", "24")
        )
        self.maintenance_log_dirs: str = os.getenv("MAINTENANCE_LOG_DIRS", "logs,tmp")
        self.maintenance_log_retention_days: int = int(
            os.getenv("MAINTENANCE_LOG_RETENTION_DAYS", "14")
        )
        self.maintenance_auto_update_enabled: bool = os.getenv(
            "MAINTENANCE_AUTO_UPDATE_ENABLED", "0"
        ) in {"1", "true", "True"}
        self.maintenance_update_command: str = os.getenv(
            "MAINTENANCE_UPDATE_COMMAND", ""
        ).strip()
        self.maintenance_disk_paths: str = os.getenv("MAINTENANCE_DISK_PATHS", ".")
        # F2.10 — Web research agent (SearXNG + summarization)
        self.research_searxng_url: str = os.getenv(
            "RESEARCH_SEARXNG_URL", "http://localhost:8080"
        ).strip()
        self.research_max_results: int = int(os.getenv("RESEARCH_MAX_RESULTS", "5"))
        self.research_fetch_timeout_seconds: int = int(
            os.getenv("RESEARCH_FETCH_TIMEOUT_SECONDS", "20")
        )
        self.research_save_dir: str = os.getenv("RESEARCH_SAVE_DIR", ".nasri-research")
        self.research_allowed_domains: str = os.getenv(
            "RESEARCH_ALLOWED_DOMAINS",
            "wikipedia.org,bbc.com,reuters.com,aa.com.tr,trthaber.com,gov.tr,edu",
        )
        # F2.12 — Anomaly detector
        self.anomaly_enabled: bool = os.getenv("ANOMALY_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        self.anomaly_network_bytes_threshold: int = int(
            os.getenv("ANOMALY_NETWORK_BYTES_THRESHOLD", "52428800")
        )
        self.anomaly_network_conn_threshold_per_minute: int = int(
            os.getenv("ANOMALY_NETWORK_CONN_THRESHOLD_PER_MINUTE", "120")
        )
        self.anomaly_file_burst_threshold_per_minute: int = int(
            os.getenv("ANOMALY_FILE_BURST_THRESHOLD_PER_MINUTE", "80")
        )
        self.anomaly_sensitive_paths: str = os.getenv(
            "ANOMALY_SENSITIVE_PATHS", "/etc,/var/lib,/home,/root,C:\\Windows,C:\\Users"
        )
        # F2.13 — Backup manager
        self.backup_enabled: bool = os.getenv("BACKUP_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        self.backup_source_paths: str = os.getenv(
            "BACKUP_SOURCE_PATHS", ".nasri-data,.nasri-rag,logs"
        )
        self.backup_output_dir: str = os.getenv("BACKUP_OUTPUT_DIR", ".nasri-backups")
        self.backup_retention_count: int = int(os.getenv("BACKUP_RETENTION_COUNT", "7"))
        self.backup_encrypt_enabled: bool = os.getenv(
            "BACKUP_ENCRYPT_ENABLED", "1"
        ) in {"1", "true", "True"}
        self.backup_remote_target: str = os.getenv("BACKUP_REMOTE_TARGET", "").strip()
        self.backup_remote_command: str = os.getenv("BACKUP_REMOTE_COMMAND", "").strip()
        # F2.14 — Driver manager
        self.driver_manager_enabled: bool = os.getenv("DRIVER_MANAGER_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        self.driver_manager_auto_install: bool = os.getenv(
            "DRIVER_MANAGER_AUTO_INSTALL", "0"
        ) in {"1", "true", "True"}
        # F3.01 — Code generator
        self.codegen_output_root: str = os.getenv("CODEGEN_OUTPUT_ROOT", ".nasri-codegen")
        # F3.04 — Zigbee/Z-Wave bridge (zigbee2mqtt)
        self.zigbee_enabled: bool = os.getenv("ZIGBEE_ENABLED", "0") in {
            "1",
            "true",
            "True",
        }
        self.zigbee2mqtt_api_url: str = os.getenv(
            "ZIGBEE2MQTT_API_URL", "http://localhost:8080"
        ).strip()
        self.zigbee2mqtt_api_key: str = os.getenv("ZIGBEE2MQTT_API_KEY", "").strip()
        # F3.06 — Proactive suggestion engine
        self.suggestion_enabled: bool = os.getenv("SUGGESTION_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        self.suggestion_max_items: int = int(os.getenv("SUGGESTION_MAX_ITEMS", "5"))
        # F3.07 — Self-heal loop
        self.self_heal_enabled: bool = os.getenv("SELF_HEAL_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        self.self_heal_auto_fix: bool = os.getenv("SELF_HEAL_AUTO_FIX", "0") in {
            "1",
            "true",
            "True",
        }
        self.self_heal_anomaly_limit: int = int(os.getenv("SELF_HEAL_ANOMALY_LIMIT", "20"))
        # F3.11 — Federation base
        self.federation_enabled: bool = os.getenv("FEDERATION_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        self.federation_node_id: str = os.getenv("FEDERATION_NODE_ID", "nasri-local").strip()
        self.federation_shared_token: str = os.getenv("FEDERATION_SHARED_TOKEN", "").strip()
        # F3.02 — Test Runner
        self.test_runner_enabled: bool = os.getenv("TEST_RUNNER_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        self.test_runner_default_target: str = os.getenv(
            "TEST_RUNNER_DEFAULT_TARGET", "tests"
        ).strip()
        self.test_runner_max_output_chars: int = int(
            os.getenv("TEST_RUNNER_MAX_OUTPUT_CHARS", "6000")
        )
        # F3.10 — Dependency Auditor
        self.dependency_auditor_enabled: bool = os.getenv(
            "DEPENDENCY_AUDITOR_ENABLED", "1"
        ) in {"1", "true", "True"}
        self.dependency_auditor_max_output_chars: int = int(
            os.getenv("DEPENDENCY_AUDITOR_MAX_OUTPUT_CHARS", "6000")
        )
        # F3.05 — Matter/Thread integration
        self.matter_enabled: bool = os.getenv("MATTER_ENABLED", "0") in {
            "1",
            "true",
            "True",
        }
        self.matter_controller_url: str = os.getenv(
            "MATTER_CONTROLLER_URL", "http://localhost:5580"
        ).strip()
        self.matter_controller_token: str = os.getenv(
            "MATTER_CONTROLLER_TOKEN", ""
        ).strip()
        # F3.12 — Beta program
        self.beta_program_enabled: bool = os.getenv("BETA_PROGRAM_ENABLED", "1") in {
            "1",
            "true",
            "True",
        }
        # F3.14 — Pricing + early access campaign
        self.pricing_currency: str = os.getenv("PRICING_CURRENCY", "TRY").strip()
        self.pricing_annual_discount_percent: int = int(
            os.getenv("PRICING_ANNUAL_DISCOUNT_PERCENT", "20")
        )
        self.pricing_early_access_extra_discount_percent: int = int(
            os.getenv("PRICING_EARLY_ACCESS_EXTRA_DISCOUNT_PERCENT", "10")
        )
        self.pricing_early_access_codes: str = os.getenv(
            "PRICING_EARLY_ACCESS_CODES", "NASRI2026,ERKEN2026"
        ).strip()

    def vault_key_bytes(self) -> bytes:
        """AES-256 için 32-byte anahtar türetir."""
        if not self.vault_master_key:
            raise ValueError("NASRI_VAULT_MASTER_KEY ayarlı değil.")
        return hashlib.sha256(self.vault_master_key.encode("utf-8")).digest()


@lru_cache
def get_settings() -> Settings:
    return Settings()
