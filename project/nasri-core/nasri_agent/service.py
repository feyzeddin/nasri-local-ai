import datetime as dt
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .config import (
    api_app_dir,
    api_port,
    install_dir,
    local_version,
    lock_file,
    state_file,
)
from .healer import heal_results
from .preflight import run_preflight
from .model_manager import run_model_research_cycle, should_research_models as should_research_models_fn
from .notifications import push as _notify
from .updater import maybe_update, should_check_update

RUNNING = True
_api_proc: subprocess.Popen | None = None  # type: ignore[type-arg]


def _handle_stop(_sig: int, _frame: object) -> None:
    global RUNNING
    RUNNING = False


def _write_state(**kwargs: str) -> None:
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


def _take_lock() -> bool:
    lock = lock_file()
    if lock.exists():
        try:
            old_pid = int(lock.read_text(encoding="utf-8").strip())
            if old_pid > 0:
                os.kill(old_pid, 0)
                return False
        except Exception:
            pass
    lock.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_lock() -> None:
    lock = lock_file()
    if lock.exists():
        lock.unlink(missing_ok=True)


def _start_api_server() -> "subprocess.Popen[bytes]":
    """Uvicorn'u arka planda subprocess olarak başlatır."""
    port = api_port()
    app_dir = api_app_dir()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
        cwd=str(app_dir),
    )
    return proc


def _stop_api_server(proc: "subprocess.Popen[bytes]") -> None:
    """Uvicorn process'ini önce SIGTERM, sonra gerekirse SIGKILL ile durdurur."""
    if proc.poll() is not None:
        return  # zaten durmuş
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _check_soul_integrity() -> None:
    """Ruh çekirdeğini doğrular; bozulmuşsa uyarır ve geri yükler."""
    try:
        from .soul import verify_core_integrity, _warn_and_revert_core
        if not verify_core_integrity():
            print("[nasri] UYARI: Ruh çekirdeği bütünlük hatası — geri yükleniyor.")
            _warn_and_revert_core()
        else:
            print("[nasri] Ruh çekirdeği bütünlüğü doğrulandı.")
    except Exception as exc:
        print(f"[nasri] Ruh çekirdeği kontrolü başarısız: {exc}")


def _ensure_ollama_running() -> None:
    """Ollama erişilebilir değilse arka planda başlatır."""
    import urllib.request as _req
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        with _req.urlopen(f"{ollama_url}/api/tags", timeout=3):
            print("[nasri] Ollama çalışıyor.")
            return
    except Exception:
        pass

    if not shutil.which("ollama"):
        print("[nasri] UYARI: 'ollama' komutu bulunamadı. Lütfen Ollama'yı kurun.")
        return

    print("[nasri] Ollama çalışmıyor, başlatılıyor...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Başlaması için bekle
    import time as _time
    for _ in range(10):
        _time.sleep(1)
        try:
            with _req.urlopen(f"{ollama_url}/api/tags", timeout=2):
                print("[nasri] Ollama başlatıldı.")
                return
        except Exception:
            pass
    print("[nasri] UYARI: Ollama 10 saniyede başlamadı, devam ediliyor.")


def _run_hardware_scan(first_run: bool = False) -> None:
    """Donanım taraması yapar. İlk çalıştırmada her zaman, sonrasında günde bir."""
    try:
        from .hardware_profile import scan_hardware, should_rescan
        if first_run or should_rescan(interval_hours=24):
            print("[nasri] Donanım taraması yapılıyor...")
            profile = scan_hardware(notify_changes=not first_run)
            cpu_model = profile.get("cpu", {}).get("model", "?")
            ram = profile.get("memory", {}).get("total_gb", "?")
            gpu_count = len(profile.get("gpu", []))
            print(f"[nasri] Donanım: CPU={cpu_model} RAM={ram}GB GPU={gpu_count} adet")
    except Exception as exc:
        print(f"[nasri] Donanım taraması başarısız: {exc}")


def _run_preflight_with_heal() -> bool:
    """Ön kontrolleri çalıştırır, hataları otomatik onarmayı dener."""
    print("[nasri] Ön kontroller çalıştırılıyor...")
    all_ok, results = run_preflight(verbose=True)

    if not all_ok:
        print("[nasri] Sorunlar tespit edildi, onarım deneniyor...")
        healed = heal_results(results)
        # Onarım sonrası tekrar kontrol et
        all_ok2, results2 = run_preflight(verbose=False)
        if not all_ok2:
            failed = [r.name for r in results2 if not r.ok]
            print(f"[nasri] UYARI: Zorunlu kontroller başarısız: {failed}")
            print("[nasri] Servis başlatma iptal edildi. Lütfen hataları manuel düzeltin.")
            return False

    print("[nasri] Ön kontroller geçti.")
    return True


def run_service() -> None:
    global _api_proc
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    if not _take_lock():
        print("Nasri servis zaten calisiyor.")
        return

    _check_soul_integrity()
    _ensure_ollama_running()

    # Saat doğruluğunu kontrol et ve gerekirse NTP senkronu yap
    try:
        from .time_sync import ensure_time_accurate
        ensure_time_accurate(verbose=True)
    except Exception as exc:
        print(f"[nasri] Zaman kontrolü başarısız: {exc}")

    _run_hardware_scan(first_run=True)

    if not _run_preflight_with_heal():
        _release_lock()
        sys.exit(1)

    port = api_port()
    _api_proc = _start_api_server()

    try:
        current_version = local_version()
        _write_state(
            status="running",
            version=__version__,
            installed_version=current_version,
            started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            platform=platform.platform(),
            api_port=str(port),
            api_pid=str(_api_proc.pid),
        )
        # Versiyon değişmişse başlangıç bildirimi gönder
        try:
            from .config import state_file as _sf
            _prev_state = json.loads(_sf().read_text(encoding="utf-8")) if _sf().exists() else {}
            _prev_version = _prev_state.get("installed_version", "")
        except Exception:
            _prev_version = ""
        if _prev_version and _prev_version != current_version:
            _notify(
                title=f"Nasrî {current_version} başlatıldı",
                message=f"Önceki sürüm: {_prev_version}",
                kind="update",
            )
        while RUNNING:
            # Uvicorn beklenmedik şekilde çöktüyse yeniden başlat
            if _api_proc.poll() is not None:
                _api_proc = _start_api_server()
                _write_state(api_pid=str(_api_proc.pid))

            # Model değişikliği veya başka bir nedenden yeniden başlatma isteği
            from .config import data_dir as _data_dir
            _restart_flag = _data_dir() / ".restart_flag"
            if _restart_flag.exists():
                try:
                    _restart_flag.unlink()
                except Exception:
                    pass
                _stop_api_server(_api_proc)
                _release_lock()
                os.execv(sys.executable, [sys.executable, "-m", "nasri_agent.service"])

            current: dict = {}
            try:
                current = json.loads(state_file().read_text(encoding="utf-8"))
            except Exception:
                current = {}

            last_checked = current.get("last_update_check")
            try:
                interval_hours = int(os.getenv("NASRI_UPDATE_INTERVAL_HOURS", "24"))
            except ValueError:
                interval_hours = 24
            if should_check_update(last_checked, interval_hours=max(1, interval_hours)):
                now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
                _write_state(last_update_check=now_iso)
                updated = maybe_update()
                if updated:
                    _write_state(
                        last_update_result="ok:updated",
                        installed_version=local_version(),
                        status="restarting",
                    )
                    # Bir sonraki terminal açılışında watch panelini tetikle
                    from .config import data_dir
                    try:
                        (data_dir() / ".open_watch_flag").touch()
                    except Exception:
                        pass
                    # Yeni kodu yüklemek için süreci yeniden başlat
                    _stop_api_server(_api_proc)
                    _release_lock()
                    os.execv(sys.executable, [sys.executable, "-m", "nasri_agent.service"])
            # Günlük donanım taraması
            _run_hardware_scan(first_run=False)

            # Günlük model araştırma döngüsü
            last_model_check = current.get("last_model_check")
            try:
                model_interval = int(os.getenv("NASRI_MODEL_CHECK_INTERVAL_HOURS", "24"))
            except ValueError:
                model_interval = 24
            if should_research_models_fn(last_model_check, interval_hours=model_interval):
                _write_state(last_model_check=dt.datetime.now(dt.timezone.utc).isoformat())
                try:
                    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
                    run_model_research_cycle(ollama_url=ollama_url)
                except Exception:
                    pass

            time.sleep(30)

        _write_state(status="stopped")
    finally:
        if _api_proc is not None:
            _stop_api_server(_api_proc)
        _release_lock()


def _run_cmd(args: list[str]) -> None:
    subprocess.run(args, check=True)


def _install_linux_service() -> None:
    service_user = (
        os.getenv("NASRI_SERVICE_USER")
        or os.getenv("SUDO_USER")
        or os.getenv("USER", "root")
    )
    data_path = Path(os.getenv("NASRI_DATA_DIR") or str(install_dir() / ".nasri-data"))
    data_path.mkdir(parents=True, exist_ok=True)

    # Şifresiz servis yönetimi için sudoers kuralı ekle
    from .device_auth import setup_sudoers
    ok, detail = setup_sudoers(service_user)
    if ok:
        print(f"Sudoers kuralı eklendi: {detail}")
    else:
        print(f"Sudoers yazılamadı ({detail}) — servis yönetiminde şifre gerekebilir")
    service_text = f"""[Unit]
Description=Nasri Background Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={service_user}
WorkingDirectory={install_dir()}
Environment=NASRI_INSTALL_DIR={install_dir()}
Environment=NASRI_DATA_DIR={data_path}
ExecStart={sys.executable} -m nasri_agent.service
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    target = Path("/etc/systemd/system/nasri.service")
    target.write_text(service_text, encoding="utf-8")
    _run_cmd(["systemctl", "daemon-reload"])
    _run_cmd(["systemctl", "enable", "nasri.service"])
    _run_cmd(["systemctl", "restart", "nasri.service"])


def _install_macos_service() -> None:
    data_path = install_dir() / ".nasri-data"
    data_path.mkdir(parents=True, exist_ok=True)
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist = launch_agents / "com.nasri.service.plist"
    content = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key>
  <string>com.nasri.service</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>-m</string>
    <string>nasri_agent.service</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>NASRI_INSTALL_DIR</key>
    <string>{install_dir()}</string>
    <key>NASRI_DATA_DIR</key>
    <string>{data_path}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>WorkingDirectory</key>
  <string>{install_dir()}</string>
</dict>
</plist>
"""
    plist.write_text(content, encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(plist)], check=False)
    _run_cmd(["launchctl", "load", str(plist)])


def _install_windows_service() -> None:
    data_path = install_dir() / ".nasri-data"
    data_path.mkdir(parents=True, exist_ok=True)
    ps = (
        '$action = New-ScheduledTaskAction -Execute "'
        + sys.executable
        + '" -Argument "-m nasri_agent.service";'
        "$trigger = New-ScheduledTaskTrigger -AtStartup;"
        "$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;"
        "[Environment]::SetEnvironmentVariable('NASRI_DATA_DIR','"
        + str(data_path)
        + "','User');"
        'Register-ScheduledTask -TaskName "NasriService" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force;'
        'Start-ScheduledTask -TaskName "NasriService";'
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def install_service() -> None:
    system = platform.system().lower()
    if system == "linux":
        _install_linux_service()
        print("Nasri service installed via systemd.")
        return
    if system == "darwin":
        _install_macos_service()
        print("Nasri service installed via launchd.")
        return
    if system == "windows":
        _install_windows_service()
        print("Nasri service installed via Task Scheduler.")
        return
    raise RuntimeError(f"Desteklenmeyen platform: {system}")


def uninstall_service() -> None:
    system = platform.system().lower()
    if system == "linux":
        subprocess.run(["systemctl", "disable", "--now", "nasri.service"], check=False)
        Path("/etc/systemd/system/nasri.service").unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], check=False)
        return
    if system == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.nasri.service.plist"
        subprocess.run(["launchctl", "unload", str(plist)], check=False)
        plist.unlink(missing_ok=True)
        return
    if system == "windows":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Unregister-ScheduledTask -TaskName 'NasriService' -Confirm:$false",
            ],
            check=False,
        )


if __name__ == "__main__":
    run_service()
