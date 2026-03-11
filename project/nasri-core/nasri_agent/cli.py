import argparse
import json
from .config import local_version, state_file


def _help_text() -> str:
    return """Nasri Komutlari:
/status   Durum kontrolu
/version  Surum bilgisi
/help     Komut listesini yazdir
/chat     Ollama ile sohbet baslat
start     Servisi foreground baslat
update    Guncelleme kontrol et ve uygula
watch         Canli bildirim panelini ac
setup-device  Cihaz anahtari ve sifresiz dogrulama kur
telegram-setup Telegram bot ayarlarini yapilandir
soul          Nasri'nin ruh durumunu goster
soul set <key> <value>  Kullanici tercihini guncelle
soul prefs    Tum kullanici tercihlerini listele
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


def cmd_chat() -> int:
    from .chat import chat_loop

    return chat_loop()


def cmd_update() -> int:
    import os
    import shutil
    import subprocess

    from .updater import local_version, maybe_update

    print(f"Mevcut surum: {local_version()}")
    print("Guncelleme kontrol ediliyor...")
    updated = maybe_update()
    if updated:
        print(f"Guncelleme tamamlandi. Yeni surum: {local_version()}")
        if shutil.which("systemctl"):
            print("Servis yeniden baslatiliyor...")
            r = subprocess.run(
                ["sudo", "systemctl", "restart", "nasri.service"],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                print("Servis yeniden baslatildi.")
            else:
                print(f"Servis baslatma basarisiz: {r.stderr.strip()}")
                print("Manuel olarak calistirin: sudo systemctl restart nasri.service")
        # Güncelleme sonrası yeni kodu yüklemek için süreci yeniden başlat
        # ve watch panelini aç (os.execv mevcut bellekteki eski kodu değil
        # diskteki yeni kodu çalıştırır)
        nasri_bin = shutil.which("nasri")
        if nasri_bin:
            os.execv(nasri_bin, [nasri_bin, "watch"])
        else:
            import sys
            os.execv(sys.executable, [sys.executable, "-m", "nasri_agent", "watch"])
    else:
        from .config import state_file
        import json
        try:
            state = json.loads(state_file().read_text(encoding="utf-8"))
            result = state.get("last_update_result", "n/a")
        except Exception:
            result = "n/a"
        if "already-latest" in result:
            print("Zaten en guncel surum.")
        else:
            print(f"Guncelleme uygulanamadi: {result}")
    return 0


def cmd_install_service() -> int:
    from .service import install_service

    install_service()
    return 0


def cmd_uninstall_service() -> int:
    from .service import uninstall_service

    uninstall_service()
    return 0


def cmd_setup_device() -> int:
    from .device_auth import run_device_setup

    return run_device_setup()


def cmd_watch() -> int:
    from .tui import run_watch

    return run_watch()


def cmd_soul(argv: list[str] | None = None) -> int:
    """Nasri'nin ruh durumunu gösterir; kullanıcı tercihlerini günceller."""
    from .soul import soul_summary, update_user_pref, get_user_prefs

    if argv:
        # nasri soul set <key> <value>
        if argv[0] == "set" and len(argv) >= 3:
            key = argv[1]
            value = " ".join(argv[2:])
            update_user_pref(key, value)
            print(f"Tercih güncellendi: {key} = {value}")
            return 0
        # nasri soul prefs
        if argv[0] == "prefs":
            import json
            print(json.dumps(get_user_prefs(), ensure_ascii=False, indent=2))
            return 0

    summary = soul_summary()
    integrity = "OK" if summary["core_intact"] else "UYARI: Ruh çekirdeği değiştirilmiş!"
    print(f"Nasrî Ruh Durumu")
    print(f"  Kimlik      : {summary['name']}")
    print(f"  Çekirdek    : v{summary['core_version']} — {integrity}")
    print(f"  Etkileşim   : {summary['interaction_count']}")
    print(f"  Tarz        : {summary['communication_style']}")
    print(f"  Dil         : {summary['language']}")
    print(f"  Yanıt uzunl.: {summary['response_length']}")
    if summary["topics"]:
        print(f"  İlgi alanl. : {', '.join(summary['topics'])}")
    if summary["expertise_notes"]:
        print(f"  Uzmanlık    : {', '.join(summary['expertise_notes'][:3])}")
    if summary["last_evolved_at"]:
        print(f"  Son evrim   : {summary['last_evolved_at'][:19]}")
    return 0


def cmd_telegram_setup() -> int:
    from .telegram_setup import run_telegram_setup

    return run_telegram_setup()


def _normalize(raw: str) -> str:
    return raw.strip().lower().replace("--", "").replace("/", "").replace("-", "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", nargs="?", default="help")
    parser.add_argument("rest", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = _normalize(args.command)
    if command == "status":
        return cmd_status()
    if command == "version":
        return cmd_version()
    if command == "help":
        return cmd_help()
    if command == "chat":
        return cmd_chat()
    if command == "start":
        return cmd_start()
    if command == "update":
        return cmd_update()
    if command == "installservice":
        return cmd_install_service()
    if command == "uninstallservice":
        return cmd_uninstall_service()
    if command == "watch":
        return cmd_watch()
    if command in {"setupdevice", "setup-device", "device"}:
        return cmd_setup_device()
    if command in {"telegramsetup", "telegram"}:
        return cmd_telegram_setup()
    if command == "soul":
        return cmd_soul(args.rest or [])

    print(f"Bilinmeyen komut: {args.command}")
    print(_help_text())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
