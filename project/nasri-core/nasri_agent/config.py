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
        return version_path.read_text(encoding="utf-8-sig").strip()
    return __version__


def api_port() -> int:
    """Uvicorn'un dinleyeceği port. NASRI_API_PORT env ile değiştirilebilir."""
    return int(os.getenv("NASRI_API_PORT", "8000"))


def deploy_key_path() -> Path:
    """Deploy SSH key dosyasının yolu (~/.nasri/.deploy_key)."""
    return install_dir().parent / ".deploy_key"


def api_app_dir() -> Path:
    """FastAPI app paketinin bulunduğu dizin (nasri-core/)."""
    # Kurulu ortamda: install_dir()/project/nasri-core
    # Geliştirme ortamında: NASRI_APP_DIR ile override edilebilir
    override = os.getenv("NASRI_APP_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return install_dir() / "project" / "nasri-core"
