"""nasri_agent service — uvicorn entegrasyonu testleri.

Gerçek uvicorn başlatılmaz; subprocess.Popen mock'lanır.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import nasri_agent.service as svc_module
from nasri_agent.cli import main as cli_main
from nasri_agent.service import _start_api_server, _stop_api_server


# ---------------------------------------------------------------------------
# _start_api_server
# ---------------------------------------------------------------------------


def test_start_api_server_calls_popen_with_uvicorn(monkeypatch, tmp_path):
    monkeypatch.setenv("NASRI_API_PORT", "9000")
    monkeypatch.setenv("NASRI_APP_DIR", str(tmp_path))

    mock_proc = MagicMock()
    mock_proc.pid = 12345

    with patch(
        "nasri_agent.service.subprocess.Popen", return_value=mock_proc
    ) as mock_popen:
        proc = _start_api_server()

    assert proc is mock_proc
    call_args = mock_popen.call_args
    cmd = call_args[0][0]
    assert "uvicorn" in cmd
    assert "app.main:app" in cmd
    assert "9000" in cmd
    assert call_args.kwargs["cwd"] == str(tmp_path)


def test_start_api_server_uses_default_port(monkeypatch, tmp_path):
    monkeypatch.delenv("NASRI_API_PORT", raising=False)
    monkeypatch.setenv("NASRI_APP_DIR", str(tmp_path))

    mock_proc = MagicMock()
    with patch("nasri_agent.service.subprocess.Popen", return_value=mock_proc):
        with patch("nasri_agent.service.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock_proc
            _start_api_server()
            cmd = mock_popen.call_args[0][0]
            assert "8000" in cmd


# ---------------------------------------------------------------------------
# _stop_api_server
# ---------------------------------------------------------------------------


def test_stop_api_server_terminates_running_process():
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # hâlâ çalışıyor

    _stop_api_server(mock_proc)

    mock_proc.terminate.assert_called_once()
    mock_proc.wait.assert_called_once_with(timeout=5)


def test_stop_api_server_kills_on_timeout():
    import subprocess as _subprocess

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.wait.side_effect = [
        _subprocess.TimeoutExpired(cmd="uvicorn", timeout=5),
        None,
    ]

    _stop_api_server(mock_proc)

    mock_proc.kill.assert_called_once()


def test_stop_api_server_noop_if_already_stopped():
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0  # zaten durmuş

    _stop_api_server(mock_proc)

    mock_proc.terminate.assert_not_called()


# ---------------------------------------------------------------------------
# run_service — api_port state.json'a yazılıyor mu?
# ---------------------------------------------------------------------------


def test_run_service_writes_api_port_to_state(monkeypatch, tmp_path):
    monkeypatch.setenv("NASRI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NASRI_API_PORT", "7777")
    monkeypatch.setenv("NASRI_APP_DIR", str(tmp_path))
    monkeypatch.setenv("NASRI_INSTALL_DIR", str(tmp_path))

    mock_proc = MagicMock()
    mock_proc.pid = 99
    mock_proc.poll.return_value = None

    # Servisi 1 döngü çalıştırıp durduralım
    def _stop_after_first_write(*_args, **_kwargs):
        svc_module.RUNNING = False

    with (
        patch("nasri_agent.service.subprocess.Popen", return_value=mock_proc),
        patch("nasri_agent.service.should_check_update", return_value=False),
        patch("nasri_agent.service._run_preflight_with_heal", return_value=True),
        patch("nasri_agent.service.time.sleep", side_effect=_stop_after_first_write),
    ):
        svc_module.RUNNING = True
        svc_module.run_service()

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["api_port"] == "7777"
    assert state["api_pid"] == "99"


# ---------------------------------------------------------------------------
# /status CLI çıktısı api_port içeriyor mu?
# ---------------------------------------------------------------------------


def test_status_shows_api_port(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NASRI_DATA_DIR", str(tmp_path))
    state = {
        "status": "running",
        "api_port": "8000",
        "last_update_result": "ok:updated",
    }
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")

    code = cli_main(["/status"])

    out = capsys.readouterr().out
    assert code == 0
    assert "api_port=8000" in out


def test_status_shows_unknown_when_no_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NASRI_DATA_DIR", str(tmp_path))

    code = cli_main(["/status"])

    out = capsys.readouterr().out
    assert code == 0
    assert "api_port=n/a" in out
