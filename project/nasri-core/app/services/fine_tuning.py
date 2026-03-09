from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from app.core.redis import get_redis
from app.core.settings import get_settings

_DATASET_PREFIX = "finetune:dataset"
_DATASET_SET = "finetune:datasets"
_JOB_PREFIX = "finetune:job"
_JOB_LIST = "finetune:jobs"


class FineTuningError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dataset_key(dataset_id: str) -> str:
    return f"{_DATASET_PREFIX}:{dataset_id}"


def _job_key(job_id: str) -> str:
    return f"{_JOB_PREFIX}:{job_id}"


def _ensure_enabled() -> None:
    if not get_settings().fine_tuning_enabled:
        raise FineTuningError("Fine-tuning pipeline devre dışı.")


def _decode(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


async def create_dataset(
    *,
    profile_id: str,
    name: str,
    source_path: str,
    format: str,
) -> dict:
    _ensure_enabled()
    dataset_id = str(uuid.uuid4())
    payload = {
        "dataset_id": dataset_id,
        "profile_id": profile_id.strip(),
        "name": name.strip(),
        "source_path": source_path.strip(),
        "format": format.strip().lower(),
        "created_at": _now_iso(),
    }
    r = get_redis()
    raw = json.dumps(payload, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.set(_dataset_key(dataset_id), raw)
    pipe.sadd(_DATASET_SET, dataset_id)
    await pipe.execute()
    return payload


async def list_datasets() -> list[dict]:
    _ensure_enabled()
    r = get_redis()
    dataset_ids = sorted(str(x) for x in await r.smembers(_DATASET_SET))
    out: list[dict] = []
    for dataset_id in dataset_ids:
        item = _decode(await r.get(_dataset_key(dataset_id)))
        if item:
            out.append(item)
    return out


async def _load_dataset(dataset_id: str) -> dict | None:
    return _decode(await get_redis().get(_dataset_key(dataset_id)))


async def start_job(
    *,
    dataset_id: str,
    epochs: int,
    lora_r: int,
    lora_alpha: int,
    learning_rate: float,
    max_steps: int,
    dry_run: bool,
) -> dict:
    _ensure_enabled()
    dataset = await _load_dataset(dataset_id)
    if dataset is None:
        raise FineTuningError("Dataset bulunamadı.")

    settings = get_settings()
    if not dry_run and not settings.fine_tuning_allow_execute:
        raise FineTuningError("Gerçek eğitim kapalı. dry_run=true kullanın.")

    output_root = Path(settings.fine_tuning_output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    output_dir = output_root / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    status = "completed" if dry_run else "running"
    detail = "Dry-run tamamlandı." if dry_run else "Eğitim başlatıldı."
    finished_at = _now_iso() if dry_run else None
    if dry_run:
        # Dry-run için örnek adapter metadata dosyası üret.
        (output_dir / "adapter_config.json").write_text(
            json.dumps(
                {
                    "base_model": settings.fine_tuning_base_model,
                    "method": "qlora",
                    "dataset_id": dataset_id,
                    "params": {
                        "epochs": epochs,
                        "lora_r": lora_r,
                        "lora_alpha": lora_alpha,
                        "learning_rate": learning_rate,
                        "max_steps": max_steps,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    payload = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "status": status,
        "base_model": settings.fine_tuning_base_model,
        "method": "qlora",
        "output_dir": str(output_dir),
        "dry_run": dry_run,
        "params": {
            "epochs": epochs,
            "lora_r": lora_r,
            "lora_alpha": lora_alpha,
            "learning_rate": learning_rate,
            "max_steps": max_steps,
        },
        "started_at": _now_iso(),
        "finished_at": finished_at,
        "detail": detail,
    }
    r = get_redis()
    raw = json.dumps(payload, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.set(_job_key(job_id), raw)
    pipe.lpush(_JOB_LIST, job_id)
    pipe.ltrim(_JOB_LIST, 0, 199)
    await pipe.execute()
    return payload


async def get_job(job_id: str) -> dict | None:
    _ensure_enabled()
    return _decode(await get_redis().get(_job_key(job_id)))


async def list_jobs(limit: int = 50) -> list[dict]:
    _ensure_enabled()
    capped = max(1, min(200, int(limit)))
    r = get_redis()
    ids = [str(x) for x in await r.lrange(_JOB_LIST, 0, capped - 1)]
    out: list[dict] = []
    for job_id in ids:
        item = _decode(await r.get(_job_key(job_id)))
        if item:
            out.append(item)
    return out

