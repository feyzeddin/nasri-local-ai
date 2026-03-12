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
setup-device          Cihaz anahtari ve 2FA dogrulama kur
setup-device sudoers  Sadece sifresiz sudo kuralini yaz (2FA gerekmez)
telegram-setup Telegram bot ayarlarini yapilandir
soul          Nasri'nin ruh durumunu goster
soul set <key> <value>  Kullanici tercihini guncelle
soul prefs    Tum kullanici tercihlerini listele
hardware      Donanim profilini goster
hardware scan Yeniden tarama yap
hardware changes  Son donanim degisikliklerini goster
hardware json Tam JSON profili yazdir
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


def cmd_update(argv: list[str] | None = None) -> int:
    import os
    import shutil
    import json as _json

    from .updater import local_version, maybe_update, install_dir
    from .config import data_dir, state_file

    sub = (argv[0] if argv else "").lower()

    # nasri update status — son güncelleme durumunu göster
    if sub == "status":
        try:
            state = _json.loads(state_file().read_text(encoding="utf-8"))
        except Exception:
            state = {}
        print(f"Kurulu sürüm : {state.get('installed_version', local_version())}")
        print(f"Son kontrol  : {state.get('last_update_check', 'hiç yapılmadı')}")
        print(f"Son sonuç    : {state.get('last_update_result', 'n/a')}")
        print(f"Repo dizini  : {install_dir()}")
        print(f"Git repo     : {'var' if (install_dir() / '.git').exists() else 'YOK — güncelleme çalışmaz!'}")
        return 0

    # nasri update reset — bir sonraki döngüde güncelleme kontrolünü zorla
    if sub == "reset":
        try:
            path = state_file()
            current = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            current["last_update_check"] = ""
            path.write_text(_json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Güncelleme zamanı sıfırlandı. Servis 30 saniye içinde kontrol edecek.")
            print("Logları takip etmek için: journalctl -u nasri.service -f")
        except Exception as e:
            print(f"Hata: {e}")
        return 0

    # nasri update — güncellemeyi hemen çalıştır
    print(f"Mevcut surum : {local_version()}")
    print(f"Repo         : {install_dir()}")
    print("Guncelleme kontrol ediliyor...")
    updated = maybe_update()
    if updated:
        print(f"Guncelleme tamamlandi. Yeni surum: {local_version()}")
        try:
            flag = data_dir() / ".restart_flag"
            flag.touch()
            print("Servis yeniden baslatma sinyali gonderildi.")
        except Exception as e:
            print(f"Restart flag yazılamadı: {e}")
        nasri_bin = shutil.which("nasri")
        if nasri_bin:
            os.execv(nasri_bin, [nasri_bin, "watch"])
        else:
            import sys
            os.execv(sys.executable, [sys.executable, "-m", "nasri_agent", "watch"])
    else:
        try:
            state = _json.loads(state_file().read_text(encoding="utf-8"))
            result = state.get("last_update_result", "n/a")
        except Exception:
            result = "n/a"
        if "already-latest" in result:
            print("Zaten en guncel surum.")
        else:
            print(f"Sonuç: {result}")
    return 0


def cmd_install_service() -> int:
    from .service import install_service

    install_service()
    return 0


def cmd_uninstall_service() -> int:
    from .service import uninstall_service

    uninstall_service()
    return 0


def cmd_setup_device(argv: list[str] | None = None) -> int:
    from .device_auth import run_device_setup, setup_sudoers, _sudoers_content
    import os
    from pathlib import Path

    # 'nasri setup-device sudoers' — sadece sudoers kuralını yaz (2FA gerekmez)
    if argv and argv[0] == "sudoers":
        user = (
            os.environ.get("SUDO_USER")
            or os.environ.get("USER")
            or "root"
        )
        print(f"Şifresiz servis yönetimi kuruluyor (kullanıcı: {user})...")
        ok, detail = setup_sudoers(user)
        if ok:
            print(f"  ✓ Sudoers kuralı yazıldı: {detail}")
            print("  Artık 'systemctl restart nasri.service' için şifre gerekmez.")
        else:
            print(f"  ✗ Başarısız: {detail}")
            print()
            print("  Manuel olarak şunu çalıştırın:")
            print(f"    sudo bash -c 'cat > /etc/sudoers.d/nasri << EOF")
            print(_sudoers_content(user).rstrip())
            print("EOF'")
            print("    sudo chmod 0440 /etc/sudoers.d/nasri")
        return 0 if ok else 1

    return run_device_setup()


def cmd_watch() -> int:
    # textual kurulu değilse otomatik kur
    try:
        import textual  # noqa: F401
    except ImportError:
        import subprocess as _sp
        import sys as _sys
        print("textual paketi bulunamadı, kuruluyor...")
        r = _sp.run(
            [_sys.executable, "-m", "pip", "install", "textual>=0.60.0", "--quiet"],
            timeout=120,
        )
        if r.returncode != 0:
            print("textual kurulamadı. Elle kurun: pip install 'textual>=0.60.0'")
            return 1
        print("textual kuruldu.")

    from .tui import run_watch
    return run_watch()


def cmd_hardware(argv: list[str] | None = None) -> int:
    """Donanım profilini gösterir veya yeniden tarar."""
    import json as _json
    from .hardware_profile import scan_hardware, get_hardware_profile, get_hardware_changes

    rescan = argv and argv[0] in ("scan", "rescan", "refresh")
    changes_only = argv and argv[0] == "changes"
    full_json = argv and argv[0] in ("json", "full")

    if changes_only:
        changes = get_hardware_changes()
        if not changes:
            print("Kayıtlı donanım değişikliği yok.")
        else:
            for c in changes[:20]:
                print(f"  [{c['detected_at'][:19]}] {c['field']}: {c['old']} → {c['new']}")
        return 0

    if rescan:
        print("Donanım taraması yapılıyor...")
        p = scan_hardware(notify_changes=True)
    else:
        p = get_hardware_profile()

    if full_json:
        print(_json.dumps(p, ensure_ascii=False, indent=2))
        return 0

    # Okunabilir özet
    print(f"\nNasrî — Donanım Profili  [{p.get('scanned_at','?')[:19]}]")
    print(f"Platform : {p.get('platform','?')}")
    os_i = p.get("os", {})
    print(f"OS       : {os_i.get('distro') or os_i.get('release','?')}")
    if os_i.get("kernel"):
        print(f"Kernel   : {os_i['kernel']}")

    cpu = p.get("cpu", {})
    if cpu:
        print(f"\nCPU      : {cpu.get('model','?')}")
        print(f"  Çekirdek (fiziksel/mantıksal): {cpu.get('cores_physical','?')}/{cpu.get('cores_logical','?')}")
        if cpu.get("freq_max_mhz"):
            print(f"  Max frekans: {cpu['freq_max_mhz']} MHz")
        if cpu.get("features"):
            print(f"  Özellikler : {', '.join(cpu['features'])}")

    mem = p.get("memory", {})
    if mem:
        print(f"\nRAM      : {mem.get('total_gb','?')} GB")
        if mem.get("swap_total_gb"):
            print(f"  Swap   : {mem['swap_total_gb']} GB")
        if mem.get("dimms"):
            for d in mem["dimms"]:
                print(f"  DIMM   : {d}")

    gpus = p.get("gpu", [])
    if gpus:
        print(f"\nGPU({len(gpus)})   :")
        for g in gpus:
            vram = f" | {g['vram_mb']//1024} GB VRAM" if g.get("vram_mb") else ""
            drv = f" | Sürücü: {g['driver']}" if g.get("driver") else ""
            print(f"  {g.get('name','?')}{vram}{drv}")

    disks = p.get("storage", [])
    if disks:
        print(f"\nDisk({len(disks)})  :")
        for d in disks:
            model = f" [{d['model']}]" if d.get("model") else ""
            dtype = f" {d.get('type','')}" if d.get("type") else ""
            total = f" {d.get('total_gb','?')} GB" if d.get("total_gb") else f" {d.get('size','')}"
            free = f" (boş: {d.get('free_gb','?')} GB)" if d.get("free_gb") else ""
            mp = f" → {d['mountpoint']}" if d.get("mountpoint") else ""
            print(f"  {d.get('device','?')}{model}{dtype}{total}{free}{mp}")

    nets = p.get("network", [])
    if nets:
        print(f"\nAğ({len(nets)})    :")
        for n in nets:
            speed = f" {n['speed_mbps']} Mbps" if n.get("speed_mbps") else ""
            ip = f" {n['ipv4']}" if n.get("ipv4") else ""
            ntype = f" [{n.get('type','')}]" if n.get("type") else ""
            status = "↑" if n.get("is_up") else "↓"
            print(f"  {status} {n['name']}{ntype}{speed}{ip}")

    usb = p.get("usb", [])
    if usb:
        print(f"\nUSB({len(usb)})   :")
        for u in usb[:8]:
            print(f"  {u}")

    changes = get_hardware_changes()
    if changes:
        print(f"\nSon değişiklikler ({len(changes)} kayıt, son 3):")
        for c in changes[:3]:
            print(f"  [{c['detected_at'][:19]}] {c['field']}: {c['old']} → {c['new']}")

    return 0


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
        return cmd_update(args.rest or [])
    if command == "installservice":
        return cmd_install_service()
    if command == "uninstallservice":
        return cmd_uninstall_service()
    if command == "watch":
        return cmd_watch()
    if command in {"setupdevice", "setup-device", "device"}:
        return cmd_setup_device(args.rest or [])
    if command in {"telegramsetup", "telegram"}:
        return cmd_telegram_setup()
    if command == "soul":
        return cmd_soul(args.rest or [])
    if command == "hardware":
        return cmd_hardware(args.rest or [])

    print(f"Bilinmeyen komut: {args.command}")
    print(_help_text())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
