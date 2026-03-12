import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import install_dir, local_version, state_file
from .notifications import push as _notify


def _run(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def _update_state(**kwargs: str) -> None:
    path = state_file()
    current: dict[str, str] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    current.update(kwargs)
    current["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _sync_env_from_example(repo: Path) -> None:
    env_example = repo / "project" / "nasri-core" / ".env.example"
    env_file = repo / "project" / "nasri-core" / ".env"
    if not env_example.exists():
        return
    if not env_file.exists():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        return

    example_lines = env_example.read_text(encoding="utf-8").splitlines()
    current_lines = env_file.read_text(encoding="utf-8").splitlines()

    known_keys: set[str] = set()
    for line in current_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        known_keys.add(stripped.split("=", 1)[0].strip())

    appended: list[str] = []
    for line in example_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key not in known_keys:
            appended.append(line)
            known_keys.add(key)

    if appended:
        content = (
            "\n".join(current_lines)
            + "\n\n# Auto-added by nasri updater\n"
            + "\n".join(appended)
            + "\n"
        )
        env_file.write_text(content, encoding="utf-8")


def _install_python_requirements(repo: Path, req_path: str) -> tuple[bool, str]:
    abs_req = (repo / req_path).resolve()
    if not abs_req.exists():
        return True, "requirements-missing:skipped"
    rc, out = _run(
        [sys.executable, "-m", "pip", "install", "-r", str(abs_req), "--quiet"],
        cwd=repo,
    )
    if rc != 0:
        return False, f"requirements-failed:{out[:180]}"
    return True, "requirements-ok"


def _install_editable(repo: Path, package_path: str) -> tuple[bool, str]:
    rc, out = _run(
        [sys.executable, "-m", "pip", "install", "-e", package_path, "--quiet"],
        cwd=repo,
    )
    if rc != 0:
        return False, f"editable-install-failed:{out[:180]}"
    return True, f"editable-ok:{package_path}"


def _run_post_update_commands(repo: Path, commands: list[str]) -> tuple[bool, str]:
    for cmd in commands:
        text = str(cmd).strip()
        if not text:
            continue
        if os.name == "nt":
            rc, out = _run(["powershell", "-Command", text], cwd=repo)
        else:
            rc, out = _run(["sh", "-lc", text], cwd=repo)
        if rc != 0:
            return False, f"post-update-failed:{text}:{out[:180]}"
    return True, "post-update-ok"


def _load_update_manifest(repo: Path) -> dict:
    manifest = _load_json(repo / "project" / "UPDATE_MANIFEST.json")
    if not manifest:
        manifest = _load_json(repo / "project" / "update-manifest.json")
    return manifest


def maybe_update() -> bool:
    repo = install_dir()
    log = lambda msg: print(f"[nasri/update] {msg}", flush=True)  # noqa: E731

    log(f"Güncelleme kontrol ediliyor... (repo: {repo})")

    if not (repo / ".git").exists():
        log(f"HATA: Git deposu bulunamadı: {repo}")
        _update_state(last_update_result="skip:no-git-repo")
        return False

    rc, fetch_out = _run(["git", "fetch", "origin", "main"], cwd=repo)
    if rc != 0:
        log(f"HATA: git fetch başarısız (rc={rc}): {fetch_out[:120]}")
        _update_state(last_update_result=f"error:fetch-failed:{fetch_out[:80]}")
        return False

    rc_local, local_head = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    rc_remote, remote_head = _run(["git", "rev-parse", "origin/main"], cwd=repo)
    if rc_local != 0 or rc_remote != 0:
        log("HATA: git rev-parse başarısız")
        _update_state(last_update_result="error:rev-parse-failed")
        return False

    local_head = local_head.strip()
    remote_head = remote_head.strip()
    log(f"Yerel: {local_head[:8]}  Uzak: {remote_head[:8]}")

    if local_head == remote_head:
        log(f"Zaten güncel ({local_version()})")
        _update_state(
            last_update_result="ok:already-latest",
            installed_version=local_version(),
        )
        return False

    log(f"Yeni commit var, indiriliyor...")
    rc_pull, pull_out = _run(["git", "pull", "--ff-only", "origin", "main"], cwd=repo)
    if rc_pull != 0:
        log(f"HATA: git pull başarısız: {pull_out[:120]}")
        _update_state(last_update_result=f"error:pull-failed:{pull_out[:120]}")
        return False

    log("Kod indirildi, paketler kuruluyor...")
    _sync_env_from_example(repo)
    manifest = _load_update_manifest(repo)
    deps = manifest.get("dependencies", {}) if isinstance(manifest, dict) else {}
    req_path = str(deps.get("python_requirements", "project/nasri-core/requirements.txt"))
    editable = deps.get("editable_packages", ["project/nasri-core"])
    editable_packages = (
        [str(x) for x in editable] if isinstance(editable, list) else ["project/nasri-core"]
    )
    post_steps = manifest.get("post_update_commands", []) if isinstance(manifest, dict) else []
    post_commands = [str(x) for x in post_steps] if isinstance(post_steps, list) else []

    ok_req, req_detail = _install_python_requirements(repo, req_path)
    if not ok_req:
        log(f"HATA: requirements kurulumu başarısız: {req_detail}")
        _update_state(last_update_result=f"error:{req_detail}")
        return False
    log(f"Requirements: {req_detail}")

    for pkg in editable_packages:
        ok_pkg, pkg_detail = _install_editable(repo, pkg)
        if not ok_pkg:
            log(f"HATA: paket kurulumu başarısız ({pkg}): {pkg_detail}")
            _update_state(last_update_result=f"error:{pkg_detail}")
            return False
        log(f"Paket kuruldu: {pkg}")

    ok_post, post_detail = _run_post_update_commands(repo, post_commands)
    if not ok_post:
        log(f"HATA: post-update komutları başarısız: {post_detail}")
        _update_state(last_update_result=f"error:{post_detail}")
        return False

    new_version = local_version()
    log(f"Güncelleme tamamlandı: {new_version}")
    _update_state(
        last_update_result="ok:updated",
        installed_version=new_version,
        update_requirements=req_detail,
        update_post_step=post_detail,
    )
    _notify(
        title=f"Nasrî {new_version} yüklendi",
        message="Yeni sürüm başarıyla güncellendi. Servis yeniden başlatılıyor.",
        kind="update",
    )
    return True


def should_check_update(last_checked_iso: str | None, interval_hours: int = 24) -> bool:
    if not last_checked_iso:
        return True
    try:
        last_checked = dt.datetime.fromisoformat(last_checked_iso)
    except ValueError:
        return True
    now = dt.datetime.now(dt.timezone.utc)
    return (now - last_checked) >= dt.timedelta(hours=interval_hours)


def remote_version_hint() -> str:
    explicit = os.getenv("NASRI_REMOTE_VERSION")
    if explicit:
        return explicit
    return "origin/main"
