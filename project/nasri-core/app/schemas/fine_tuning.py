from __future__ import annotations

from pydantic import BaseModel, Field


class FineTuningDatasetCreateRequest(BaseModel):
    profile_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    source_path: str = Field(min_length=1, max_length=512)
    format: str = Field(default="jsonl", min_length=1, max_length=32)


class FineTuningDataset(BaseModel):
    dataset_id: str
    profile_id: str
    name: str
    source_path: str
    format: str
    created_at: str


class FineTuningDatasetListResponse(BaseModel):
    count: int
    items: list[FineTuningDataset]


class FineTuningJobStartRequest(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=64)
    epochs: int = Field(default=3, ge=1, le=20)
    lora_r: int = Field(default=16, ge=4, le=256)
    lora_alpha: int = Field(default=32, ge=4, le=512)
    learning_rate: float = Field(default=0.0002, gt=0, le=0.1)
    max_steps: int = Field(default=500, ge=50, le=50000)
    dry_run: bool = True


class FineTuningJob(BaseModel):
    job_id: str
    dataset_id: str
    status: str
    base_model: str
    method: str
    output_dir: str
    dry_run: bool
    params: dict
    started_at: str
    finished_at: str | None = None
    detail: str | None = None


class FineTuningJobListResponse(BaseModel):
    count: int
    items: list[FineTuningJob]

