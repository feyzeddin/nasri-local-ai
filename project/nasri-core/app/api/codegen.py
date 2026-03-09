from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.codegen import CodegenFile, CodegenGenerateRequest, CodegenGenerateResponse
from app.services.codegen import CodegenError, generate_project

router = APIRouter(prefix="/codegen", tags=["codegen"])


@router.post("/generate", response_model=CodegenGenerateResponse)
def codegen_generate(
    body: CodegenGenerateRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> CodegenGenerateResponse:
    try:
        out = generate_project(
            project_name=body.project_name,
            requirement=body.requirement,
            language=body.language,
            framework=body.framework,
        )
    except CodegenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CodegenGenerateResponse(
        project_name=out.project_name,
        output_dir=out.output_dir,
        files=[CodegenFile(path=p) for p in out.files],
    )
