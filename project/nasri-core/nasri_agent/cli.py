import argparse
import json
from .config import local_version, state_file


def _help_text() -> str:
    return """Nasri Komutlari:
/status   Durum kontrolu
/version  Surum bilgisi
/help     Komut listesini yazdir
start     Servisi foreground baslat
"""


def _load_state() -> dict:
    path = state_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def cmd_status() -> int:
    print("Selamunaleyküm ben Nasrî")
    state = _load_state()
    if state:
        status = state.get("status", "unknown")
        last_update = state.get("last_update_result", "n/a")
        api_port = state.get("api_port", "n/a")
        print(f"status={status} api_port={api_port} last_update={last_update}")
    else:
        print("status=unknown api_port=n/a last_update=n/a")
    return 0


def cmd_version() -> int:
    print(f"nasri {local_version()}")
    return 0


def cmd_help() -> int:
    print(_help_text())
    return 0


def cmd_start() -> int:
    from .service import run_service

    run_service()
    return 0


def cmd_install_service() -> int:
    from .service import install_service

    install_service()
    return 0


def cmd_uninstall_service() -> int:
    from .service import uninstall_service

    uninstall_service()
    return 0


def _normalize(raw: str) -> str:
    return raw.strip().lower().replace("--", "").replace("/", "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", nargs="?", default="help")
    args = parser.parse_args(argv)

    command = _normalize(args.command)
    if command == "status":
        return cmd_status()
    if command == "version":
        return cmd_version()
    if command == "help":
        return cmd_help()
    if command == "start":
        return cmd_start()
    if command == "installservice":
        return cmd_install_service()
    if command == "uninstallservice":
        return cmd_uninstall_service()

    print(f"Bilinmeyen komut: {args.command}")
    print(_help_text())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
