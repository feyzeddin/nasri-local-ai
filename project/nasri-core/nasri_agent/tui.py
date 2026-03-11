"""
tui.py — Nasrî interaktif terminal paneli.

Kullanım: nasri watch
Gereksinim: textual>=0.60.0 (requirements.txt'te tanımlı)

Layout:
  ┌─────────────────── Nasrî v0.x ● running ────────────────────┐
  │  💬 Sohbet                    │  🔔 Bildirimler             │
  │                               │                             │
  │  Nasrî: Selamlar!             │  ↑ v0.3.0 yüklendi         │
  │  Sen: merhaba                 │  i Servis başlatıldı        │
  │                               │                             │
  ├───────────────────────────────┴─────────────────────────────┤
  │  > mesajınızı yazın...                                      │
  └─────────────────────────────────────────────────────────────┘
  Ctrl+C çık  Ctrl+U güncelle  Ctrl+N bildirimleri temizle
"""
from __future__ import annotations

import hashlib
import json
import uuid

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Input, Label, RichLog, Static

from .config import local_version, state_file
from .notifications import list_all, mark_all_read

_SESSION_ID = str(uuid.uuid4())

_KIND_COLOR = {
    "update": "green",
    "info": "cyan",
    "action": "yellow",
    "error": "red",
    "warning": "yellow",
}
_KIND_ICON = {
    "update": "↑",
    "info": "i",
    "action": "!",
    "error": "✗",
    "warning": "⚠",
}


def _load_state() -> dict:
    path = state_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class NasriApp(App[None]):
    CSS = """
Screen {
    layout: vertical;
    background: $surface;
}

#status_bar {
    height: 1;
    background: $primary-darken-2;
    color: $text;
    padding: 0 1;
}

#main {
    layout: horizontal;
    height: 1fr;
}

#chat_panel {
    width: 2fr;
    border: solid $primary;
}

#chat_title {
    background: $primary-darken-2;
    height: 1;
    padding: 0 1;
    color: $text;
}

#chat_log {
    height: 1fr;
    padding: 0 1;
}

#notif_panel {
    width: 1fr;
    border: solid $secondary;
}

#notif_title {
    background: $secondary-darken-2;
    height: 1;
    padding: 0 1;
    color: $text;
}

#notif_log {
    height: 1fr;
    padding: 0 1;
}

#chat_input {
    height: 3;
    border-top: solid $primary;
}
"""

    BINDINGS = [
        Binding("ctrl+c", "quit", "Çık"),
        Binding("ctrl+u", "do_update", "Güncelle"),
        Binding("ctrl+n", "clear_notifs", "Bildirimleri Temizle"),
    ]

    _last_notif_hash: str = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="status_bar")
        with Horizontal(id="main"):
            with Vertical(id="chat_panel"):
                yield Label("💬 Sohbet", id="chat_title")
                yield RichLog(id="chat_log", markup=True, highlight=False, wrap=True)
            with Vertical(id="notif_panel"):
                yield Label("🔔 Bildirimler", id="notif_title")
                yield RichLog(id="notif_log", markup=True, highlight=False, wrap=True)
        yield Input(placeholder="Nasrî ile konuş... (Enter ile gönder)", id="chat_input")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_status()
        self._refresh_notifications()
        self.set_interval(3, self._refresh_status)
        self.set_interval(3, self._refresh_notifications)
        chat_log = self.query_one("#chat_log", RichLog)
        chat_log.write("[bold cyan]Nasrî:[/bold cyan] Selamunaleyküm! Size nasıl yardımcı olabilirim?")
        self.query_one("#chat_input", Input).focus()

    # ------------------------------------------------------------------ #
    # Durum çubuğu
    # ------------------------------------------------------------------ #

    def _refresh_status(self) -> None:
        state = _load_state()
        status = state.get("status", "unknown")
        version = local_version()
        port = state.get("api_port", "n/a")
        last_update = state.get("last_update_result", "n/a")
        color = "green" if status == "running" else "red"
        self.query_one("#status_bar", Static).update(
            f"[bold]Nasrî[/bold] v{version}  "
            f"[{color}]● {status}[/{color}]  "
            f"port:{port}  güncelleme:{last_update}"
        )

    # ------------------------------------------------------------------ #
    # Bildirimler
    # ------------------------------------------------------------------ #

    def _refresh_notifications(self) -> None:
        notifications = list_all()

        # Sadece değişiklik varsa yeniden çiz
        sig = hashlib.md5(
            json.dumps([(n.get("id"), n.get("read")) for n in notifications]).encode()
        ).hexdigest()
        if sig == self._last_notif_hash:
            return
        self._last_notif_hash = sig

        unread = sum(1 for n in notifications if not n.get("read"))
        self.query_one("#notif_title", Label).update(f"🔔 Bildirimler ({unread} yeni)")

        notif_log = self.query_one("#notif_log", RichLog)
        notif_log.clear()

        if not notifications:
            notif_log.write("[dim]Henüz bildirim yok[/dim]")
            return

        for n in notifications[:30]:
            kind = n.get("kind", "info")
            color = _KIND_COLOR.get(kind, "white")
            icon = _KIND_ICON.get(kind, " ")
            dot = "[bold yellow]•[/bold yellow] " if not n.get("read") else "  "
            ts = n.get("timestamp", "")
            try:
                from datetime import datetime
                ts_str = datetime.fromisoformat(ts).strftime("%m-%d %H:%M")
            except Exception:
                ts_str = ts[:16]

            notif_log.write(
                f"{dot}[{color}]{icon} {n.get('title', '')}[/{color}] [dim]{ts_str}[/dim]"
            )
            msg = n.get("message", "")
            if msg:
                notif_log.write(f"   [dim]{msg}[/dim]")

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #

    # Streaming sırasında input kilidi
    _responding: bool = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._responding:
            return
        message = event.value.strip()
        if not message:
            return
        event.input.value = ""
        self.query_one("#chat_log", RichLog).write(
            f"[bold white]Sen:[/bold white] {message}"
        )
        self._stream_message(message)

    @work(thread=True)
    def _stream_message(self, message: str) -> None:
        """SSE stream ile Ollama'dan yanıt alır, token token gösterir."""
        self.call_from_thread(self._set_responding, True)

        state = _load_state()
        port = state.get("api_port", "8000")
        url = f"http://localhost:{port}/chat/stream"

        chunks: list[str] = []
        error: str | None = None

        try:
            timeout = httpx.Timeout(connect=5.0, read=45.0, write=5.0, pool=5.0)
            with httpx.Client(timeout=timeout) as client:
                with client.stream(
                    "POST",
                    url,
                    json={"message": message, "session_id": _SESSION_ID},
                ) as resp:
                    if resp.status_code != 200:
                        error = f"Sunucu hatası ({resp.status_code}). Servis çalışıyor mu?"
                    else:
                        # SSE satırlarını oku, token token göster
                        for line in resp.iter_lines():
                            if not line.startswith("data: "):
                                continue
                            chunk = line[6:]
                            if chunk == "[DONE]":
                                break
                            if chunk.startswith("[ERROR]"):
                                error = chunk[7:].strip() or "Bilinmeyen hata"
                                break
                            if chunk:
                                chunks.append(chunk)
                                # Her ~5 tokende bir UI'ı güncelle (çok sık çağrı engellenir)
                                if len(chunks) % 5 == 0:
                                    self.call_from_thread(
                                        self._update_streaming_reply, "".join(chunks)
                                    )
        except httpx.ConnectError:
            error = "API'ye bağlanılamadı. Nasrî servisi çalışıyor mu? (nasri start)"
        except httpx.ReadTimeout:
            error = "Zaman aşımı (45s). Ollama çok yavaş ya da yanıt vermiyor."
        except Exception as exc:
            error = f"Bağlantı hatası: {exc}"

        reply = error or "".join(chunks) or "(boş yanıt)"
        self.call_from_thread(self._finish_reply, reply, is_error=bool(error))

    def _set_responding(self, state: bool) -> None:
        self._responding = state
        inp = self.query_one("#chat_input", Input)
        inp.placeholder = "Nasrî yanıtlıyor..." if state else "Nasrî ile konuş... (Enter ile gönder)"
        inp.disabled = state

    def _update_streaming_reply(self, partial: str) -> None:
        """Streaming sırasında durum çubuğunda kısa özet göster."""
        bar = self.query_one("#status_bar", Static)
        preview = partial[-40:].replace("\n", " ")
        bar.update(f"[dim]Nasrî: ...{preview}[/dim]")

    def _finish_reply(self, reply: str, is_error: bool = False) -> None:
        chat_log = self.query_one("#chat_log", RichLog)
        if is_error:
            chat_log.write(f"[bold cyan]Nasrî:[/bold cyan] [red]{reply}[/red]")
        else:
            chat_log.write(f"[bold cyan]Nasrî:[/bold cyan] {reply}")
        self._set_responding(False)
        self._refresh_status()
        self.query_one("#chat_input", Input).focus()

    # ------------------------------------------------------------------ #
    # Eylemler
    # ------------------------------------------------------------------ #

    def action_do_update(self) -> None:
        self._run_update()

    @work(thread=True)
    def _run_update(self) -> None:
        from .updater import local_version as lv, maybe_update
        self.call_from_thread(self._write_chat, "[dim]Güncelleme kontrol ediliyor...[/dim]")
        updated = maybe_update()
        msg = (
            f"[green]Güncelleme tamamlandı: {lv()}[/green]"
            if updated
            else "[dim]Zaten en güncel sürüm.[/dim]"
        )
        self.call_from_thread(self._write_chat, msg)
        self.call_from_thread(self._refresh_status)
        self.call_from_thread(self._refresh_notifications)

    def action_clear_notifs(self) -> None:
        mark_all_read()
        self._last_notif_hash = ""
        self._refresh_notifications()

    def _write_chat(self, msg: str) -> None:
        self.query_one("#chat_log", RichLog).write(msg)

    def _append_reply(self, reply: str) -> None:
        """Eski non-streaming yol — artık kullanılmıyor, geriye dönük uyumluluk için."""
        self._finish_reply(reply)

    def on_unmount(self) -> None:
        mark_all_read()


def run_watch() -> int:
    try:
        from textual.app import App  # noqa: F401
    except ImportError:
        print("'textual' paketi eksik. Kurmak için: pip install textual")
        return 1
    NasriApp().run()
    return 0
