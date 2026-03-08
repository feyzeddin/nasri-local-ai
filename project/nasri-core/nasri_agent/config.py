import os
from pathlib import Path

from . import __version__


def data_dir() -> Path:
    root = os.getenv("NASRI_DATA_DIR")
    if root:
        path = Path(root).expanduser().resolve()
    else:
        path = Path.home() / ".nasri"
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except PermissionError:
        fallback = Path.cwd() / ".nasri-data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def state_file() -> Path:
    return data_dir() / "state.json"


def lock_file() -> Path:
    return data_dir() / "service.lock"


def install_dir() -> Path:
    root = os.getenv("NASRI_INSTALL_DIR")
    if root:
        return Path(root).expanduser().resolve()
    return Path.home() / ".nasri" / "src"


def repo_version_file() -> Path:
    return install_dir() / "project" / "VERSION"


def local_version() -> str:
    version_path = repo_version_file()
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return __version__
