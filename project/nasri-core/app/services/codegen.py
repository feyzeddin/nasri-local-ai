from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from app.core.settings import get_settings


class CodegenError(Exception):
    pass


@dataclass
class GeneratedProject:
    project_name: str
    output_dir: str
    files: list[str]


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise CodegenError("Geçersiz proje adı.")
    return slug[:80]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _python_fastapi_template(project_name: str, requirement: str) -> dict[str, str]:
    return {
        "README.md": f"# {project_name}\n\n## Gereksinim\n\n{requirement}\n",
        "app/main.py": (
            'from fastapi import FastAPI\n\n'
            f'app = FastAPI(title="{project_name}")\n\n'
            '@app.get("/health")\n'
            'def health() -> dict[str, str]:\n'
            '    return {"status": "ok"}\n'
        ),
        "requirements.txt": "fastapi\nuvicorn\n",
    }


def _python_plain_template(project_name: str, requirement: str) -> dict[str, str]:
    return {
        "README.md": f"# {project_name}\n\n## Gereksinim\n\n{requirement}\n",
        "main.py": 'def main() -> None:\n    print("hello from nasri codegen")\n\n\nif __name__ == "__main__":\n    main()\n',
    }


def _typescript_express_template(project_name: str, requirement: str) -> dict[str, str]:
    return {
        "README.md": f"# {project_name}\n\n## Gereksinim\n\n{requirement}\n",
        "src/index.ts": (
            'import express from "express";\n\n'
            f'const app = express();\nconst port = process.env.PORT || 3000;\n\n'
            'app.get("/health", (_req, res) => res.json({ status: "ok" }));\n\n'
            'app.listen(port, () => console.log(`server on ${port}`));\n'
        ),
        "package.json": (
            "{\n"
            f'  "name": "{_slug(project_name)}",\n'
            '  "version": "0.1.0",\n'
            '  "private": true,\n'
            '  "type": "module",\n'
            '  "scripts": { "dev": "node --loader ts-node/esm src/index.ts" },\n'
            '  "dependencies": { "express": "^4.19.2" }\n'
            "}\n"
        ),
    }


def _typescript_plain_template(project_name: str, requirement: str) -> dict[str, str]:
    return {
        "README.md": f"# {project_name}\n\n## Gereksinim\n\n{requirement}\n",
        "src/index.ts": 'console.log("hello from nasri codegen");\n',
        "package.json": (
            "{\n"
            f'  "name": "{_slug(project_name)}",\n'
            '  "version": "0.1.0",\n'
            '  "private": true,\n'
            '  "type": "module"\n'
            "}\n"
        ),
    }


def generate_project(
    project_name: str,
    requirement: str,
    language: str,
    framework: str,
) -> GeneratedProject:
    name = project_name.strip()
    if not name:
        raise CodegenError("project_name boş olamaz.")
    req = " ".join(requirement.strip().split())
    if not req:
        raise CodegenError("requirement boş olamaz.")

    root = Path(get_settings().codegen_output_root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dir_name = f"{_slug(name)}-{ts}"
    out_dir = root / dir_name
    out_dir.mkdir(parents=True, exist_ok=True)

    lang = language.strip().lower()
    fw = framework.strip().lower()

    if lang == "python":
        templates = (
            _python_fastapi_template(name, req)
            if fw == "fastapi"
            else _python_plain_template(name, req)
        )
    elif lang == "typescript":
        templates = (
            _typescript_express_template(name, req)
            if fw == "express"
            else _typescript_plain_template(name, req)
        )
    else:
        raise CodegenError("Desteklenmeyen dil.")

    files: list[str] = []
    for rel_path, content in templates.items():
        p = out_dir / rel_path
        _write(p, content)
        files.append(str(p))

    return GeneratedProject(project_name=name, output_dir=str(out_dir), files=files)
