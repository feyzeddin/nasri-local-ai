from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CodegenGenerateRequest(BaseModel):
    project_name: str = Field(min_length=2, max_length=80)
    requirement: str = Field(min_length=5, max_length=4000)
    language: Literal["python", "typescript"] = "python"
    framework: Literal["fastapi", "flask", "express", "none"] = "fastapi"


class CodegenFile(BaseModel):
    path: str


class CodegenGenerateResponse(BaseModel):
    project_name: str
    output_dir: str
    files: list[CodegenFile]
