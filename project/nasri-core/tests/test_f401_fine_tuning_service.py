from __future__ import annotations

from pathlib import Path

import fakeredis.aioredis as fakeredis
import pytest

import app.services.fine_tuning as ft_module


class _Settings:
    fine_tuning_enabled = True
    fine_tuning_base_model = "llama3"
    fine_tuning_output_dir = ".tmp-finetune"
    fine_tuning_allow_execute = False


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    fake = fakeredis.FakeRedis(decode_responses=True)
    s = _Settings()
    s.fine_tuning_output_dir = str(tmp_path / "finetune")
    monkeypatch.setattr(ft_module, "get_redis", lambda: fake)
    monkeypatch.setattr(ft_module, "get_settings", lambda: s)
    return fake


@pytest.mark.asyncio
async def test_fine_tuning_dataset_and_dry_run_job(tmp_path):
    ds = await ft_module.create_dataset(
        profile_id="feyza",
        name="profil data",
        source_path=str(tmp_path / "dataset.jsonl"),
        format="jsonl",
    )
    assert ds["profile_id"] == "feyza"

    listed = await ft_module.list_datasets()
    assert len(listed) == 1

    job = await ft_module.start_job(
        dataset_id=ds["dataset_id"],
        epochs=3,
        lora_r=16,
        lora_alpha=32,
        learning_rate=0.0002,
        max_steps=500,
        dry_run=True,
    )
    assert job["status"] == "completed"
    assert Path(job["output_dir"]).exists()
    assert (Path(job["output_dir"]) / "adapter_config.json").exists()

    job_out = await ft_module.get_job(job["job_id"])
    assert job_out is not None
    assert job_out["job_id"] == job["job_id"]


@pytest.mark.asyncio
async def test_non_dry_run_requires_permission(tmp_path):
    ds = await ft_module.create_dataset(
        profile_id="feyza",
        name="profil data",
        source_path=str(tmp_path / "dataset.jsonl"),
        format="jsonl",
    )
    with pytest.raises(ft_module.FineTuningError, match="dry_run=true"):
        await ft_module.start_job(
            dataset_id=ds["dataset_id"],
            epochs=3,
            lora_r=16,
            lora_alpha=32,
            learning_rate=0.0002,
            max_steps=500,
            dry_run=False,
        )

