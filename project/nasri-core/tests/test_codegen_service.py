from __future__ import annotations

from pathlib import Path

import pytest

import app.services.codegen as cg_module


class _Settings:
    codegen_output_root = ""


def test_generate_project_fastapi(tmp_path, monkeypatch):
    s = _Settings()
    s.codegen_output_root = str(tmp_path)
    monkeypatch.setattr(cg_module, "get_settings", lambda: s)

    out = cg_module.generate_project(
        project_name="Nasri Demo",
        requirement="Basit bir sağlık endpointi olsun",
        language="python",
        framework="fastapi",
    )
    assert Path(out.output_dir).exists()
    assert any(p.endswith("app\\main.py") or p.endswith("app/main.py") for p in out.files)


def test_generate_project_invalid_name():
    with pytest.raises(cg_module.CodegenError):
        cg_module.generate_project(
            project_name=" ",
            requirement="x",
            language="python",
            framework="fastapi",
        )
