from __future__ import annotations

from pathlib import Path

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
import app.services.memory as memory_module
import app.services.vault as vault_module


class _Settings:
    def __init__(self) -> None:
        self.redis_host = "localhost"
        self.redis_port = 6379
        self.ollama_url = "http://localhost:11434"
        self.model_name = "llama3"
        self.max_history_pairs = 10
        self.session_ttl_seconds = 3600
        self.system_prompt = None
        self.api_key = None
        self.cors_origins = ["http://localhost:5173"]
        self.rate_limit_rpm = 60
        self.rbac_enabled = False
        self.auth_session_ttl_seconds = 3600
        self.users = {}
        self.files_root = "."
        self.files_max_results = 200
        self.whisper_cpp_binary = "whisper"
        self.whisper_cpp_model = "model.bin"
        self.whisper_cpp_language = "tr"
        self.whisper_cpp_timeout_seconds = 120
        self.piper_binary = "piper"
        self.piper_model = "model.onnx"
        self.piper_output_sample_rate = 22050
        self.piper_timeout_seconds = 120
        self.vault_master_key = "super-secret-master-key"
        self.vault_key_id = "v1"
        self.device_fingerprint_salt = "device-salt"
        self.biometric_salt = "bio-salt"
        self.rag_collection_name = "nasri_docs"
        self.rag_persist_dir = ".nasri-rag"
        self.rag_embedding_model = "nomic-embed-text"
        self.rag_default_top_k = 5
        self.memory_collection_name = "nasri_memory"
        self.memory_default_top_k = 5
        self.planner_max_steps = 6
        self.model_router_tier_order = "local,free,paid"
        self.model_router_free_enabled = True
        self.model_router_free_api_url = ""
        self.model_router_free_api_key = ""
        self.model_router_free_model = ""
        self.model_router_paid_enabled = False
        self.model_router_paid_api_url = ""
        self.model_router_paid_api_key = ""
        self.model_router_paid_model = ""
        self.model_router_free_provider = "groq"
        self.model_router_paid_provider = "openrouter"
        self.external_ai_anonymize_enabled = True
        self.groq_api_key = ""
        self.groq_api_url = ""
        self.groq_model = ""
        self.groq_rpm = 60
        self.groq_cost_input_per_1k = 0.0
        self.groq_cost_output_per_1k = 0.0
        self.gemini_api_key = ""
        self.gemini_api_url = ""
        self.gemini_model = ""
        self.gemini_rpm = 60
        self.gemini_cost_input_per_1k = 0.0
        self.gemini_cost_output_per_1k = 0.0
        self.openrouter_api_key = ""
        self.openrouter_api_url = ""
        self.openrouter_model = ""
        self.openrouter_rpm = 60
        self.openrouter_cost_input_per_1k = 0.0
        self.openrouter_cost_output_per_1k = 0.0
        self.lan_scan_default_cidr = "192.168.1.0/24"
        self.lan_scan_timeout_seconds = 30
        self.lan_scan_mdns_enabled = True
        self.ssh_connect_timeout_seconds = 15
        self.home_assistant_enabled = False
        self.home_assistant_url = "http://localhost:8123"
        self.home_assistant_token = ""
        self.home_assistant_default_area = "salon"
        self.mqtt_enabled = True
        self.mqtt_host = "localhost"
        self.mqtt_port = 1883
        self.mqtt_username = ""
        self.mqtt_password = ""
        self.mqtt_topic_prefix = "nasri"
        self.maintenance_enabled = True
        self.maintenance_interval_hours = 24
        self.maintenance_log_dirs = "logs,tmp"
        self.maintenance_log_retention_days = 14
        self.maintenance_auto_update_enabled = False
        self.maintenance_update_command = ""
        self.maintenance_disk_paths = "."
        self.research_searxng_url = "http://localhost:8080"
        self.research_max_results = 5
        self.research_fetch_timeout_seconds = 20
        self.research_save_dir = ".nasri-research"
        self.research_allowed_domains = "wikipedia.org,reuters.com"
        self.anomaly_enabled = True
        self.anomaly_network_bytes_threshold = 100
        self.anomaly_network_conn_threshold_per_minute = 5
        self.anomaly_file_burst_threshold_per_minute = 5
        self.anomaly_sensitive_paths = "/etc,C:\\Windows"
        self.backup_enabled = True
        self.backup_source_paths = "."
        self.backup_output_dir = ".nasri-backups"
        self.backup_retention_count = 7
        self.backup_encrypt_enabled = True
        self.backup_remote_target = ""
        self.backup_remote_command = ""
        self.driver_manager_enabled = True
        self.driver_manager_auto_install = False
        self.codegen_output_root = ".nasri-codegen-test"

    def vault_key_bytes(self) -> bytes:
        import hashlib

        return hashlib.sha256(self.vault_master_key.encode("utf-8")).digest()


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    monkeypatch.setattr(security_module, "get_redis", lambda: fake)
    monkeypatch.setattr(identity_module, "get_redis", lambda: fake)
    monkeypatch.setattr(vault_module, "get_redis", lambda: fake)
    return fake


def _make_client(monkeypatch, settings: _Settings) -> TestClient:
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    monkeypatch.setattr(vault_module, "get_settings", lambda: settings)
    monkeypatch.setattr(memory_module, "get_settings", lambda: settings)
    import app.api.files as files_module
    import app.api.speech as speech_module
    import app.main as main_module

    monkeypatch.setattr(files_module, "get_settings", lambda: settings)
    monkeypatch.setattr(speech_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "start_maintenance_worker", lambda: None)

    async def _noop_stop() -> None:
        return

    monkeypatch.setattr(main_module, "stop_maintenance_worker", _noop_stop)
    app = main_module._create_app()
    return TestClient(app)


def test_codegen_generate(monkeypatch, tmp_path):
    settings = _Settings()
    settings.codegen_output_root = str(tmp_path)
    client = _make_client(monkeypatch, settings)
    resp = client.post(
        "/codegen/generate",
        json={
            "project_name": "Alpha",
            "requirement": "sağlık endpointi üret",
            "language": "python",
            "framework": "fastapi",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert Path(data["output_dir"]).exists()
    assert len(data["files"]) >= 2
