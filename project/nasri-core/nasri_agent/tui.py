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

try:
    from textual import work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.reactive import reactive
    from textual.widgets import Footer, Input, Label, RichLog, Static
    _TEXTUAL_OK = True
except ImportError:
    _TEXTUAL_OK = False
    # textual yoksa sınıf tanımlarını çöktürmemek için stub'lar
    class App:  # type: ignore[no-redef]
        pass
    class ComposeResult:  # type: ignore[no-redef]
        pass
    class Binding:  # type: ignore[no-redef]
        def __init__(self, *a: object, **kw: object) -> None: pass
    class Horizontal:  # type: ignore[no-redef]
        pass
    class Vertical:  # type: ignore[no-redef]
        pass
    def reactive(*a: object, **kw: object) -> object: return None  # type: ignore[misc]
    class Footer: pass  # type: ignore[no-redef]
    class Input:  # type: ignore[no-redef]
        pass
    class Label:  # type: ignore[no-redef]
        pass
    class RichLog:  # type: ignore[no-redef]
        pass
    class Static:  # type: ignore[no-redef]
        pass
    def work(f: object) -> object: return f  # type: ignore[misc]

from .config import local_version, state_file
from .notifications import list_all, mark_all_read

_SESSION_ID = str(uuid.uuid4())

# ------------------------------------------------------------------ #
# Yerel yanıtlayıcı — API'ye gitmeye gerek olmayan sorular
# ------------------------------------------------------------------ #

import re as _re

_DATE_PATTERNS = _re.compile(
    r"\b(tarih|bugün|bu gün|bugünün tarihi|günün tarihi|hangi gün|"
    r"today|what.*date|kaçıncı|ayın kaçı)\b",
    _re.IGNORECASE,
)
_TIME_PATTERNS = _re.compile(
    r"\b(saat|zaman|şu an|şuan|saat kaç|time|what time|saati)\b",
    _re.IGNORECASE,
)
_BOTH_PATTERNS = _re.compile(
    r"\b(tarih.*saat|saat.*tarih|şu anki|şu an ki|now|şimdi)\b",
    _re.IGNORECASE,
)
_WEATHER_PATTERNS = _re.compile(
    r"\b(hava|hava durumu|hava nasıl|sıcaklık|derece|yağmur|kar|fırtına|"
    r"weather|temperature|forecast|nem|rüzgar)\b",
    _re.IGNORECASE,
)


def _extract_city(message: str) -> str:
    """Mesajdan şehir adını çıkarır. Bulamazsa 'Turkey' döner."""
    # "Ankara'da", "İstanbul'da", "Bursa'ta" gibi konum ekleri
    m = _re.search(
        r"\b([A-ZÇĞİÖŞÜ][a-zçğışöşü]{1,}(?:\s[A-ZÇĞİÖŞÜ][a-zçğışöşü]+)?)"
        r"['\u2019]?(da|de|ta|te|nda|nde|nta|nte)\b",
        message,
    )
    if m:
        return m.group(1)
    # "İstanbul hava" — hava kelimesinden önceki büyük harfli kelime
    m = _re.search(
        r"\b([A-ZÇĞİÖŞÜ][a-zçğışöşü]{1,}(?:\s[A-ZÇĞİÖŞÜ][a-zçğışöşü]+)?)"
        r"\s+(?:hava|sıcaklık|weather)",
        message,
    )
    if m:
        return m.group(1)
    return "Turkey"


def _fetch_weather(city: str) -> str:
    """wttr.in'den hava durumu çeker (ücretsiz, API key yok)."""
    import urllib.request, urllib.parse, json as _json
    try:
        encoded = urllib.parse.quote(city)
        url = f"http://wttr.in/{encoded}?format=j1&lang=tr"
        req = urllib.request.Request(url, headers={"User-Agent": "Nasri/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read().decode())

        cur = data["current_condition"][0]
        area = data["nearest_area"][0]

        city_name = (
            area.get("areaName", [{}])[0].get("value", city)
            or city
        )
        temp_c    = cur.get("temp_C", "?")
        feels_c   = cur.get("FeelsLikeC", "?")
        humidity  = cur.get("humidity", "?")
        wind_kmph = cur.get("windspeedKmph", "?")
        desc_list = cur.get("lang_tr") or cur.get("weatherDesc", [{}])
        desc      = desc_list[0].get("value", "?") if desc_list else "?"

        # Bugünkü min/max
        today = data.get("weather", [{}])[0]
        min_c = today.get("mintempC", "?")
        max_c = today.get("maxtempC", "?")

        return (
            f"{city_name} hava durumu: {desc}, {temp_c}°C "
            f"(hissedilen {feels_c}°C) | "
            f"Min: {min_c}°C  Maks: {max_c}°C | "
            f"Nem: %{humidity}  Rüzgar: {wind_kmph} km/s"
        )
    except Exception as exc:
        return f"Hava durumu alınamadı: {exc}"


def _normalize_query(text: str) -> str:
    """
    Sorguda küçük yazım hatalarını giderir:
    - Ardışık tekrar eden harfleri teke indirir (ssaat→saat, haava→hava)
    - Küçük harfe çevirir
    """
    import re as _r
    return _r.sub(r'(.)\1+', r'\1', text.lower().strip())


def _try_local_answer(message: str) -> str | None:
    """
    Tarih/saat/hava durumu gibi sorguları Ollama'ya iletmeden yanıtlar.
    Yazım hataları normalize edilerek eşleştirme yapılır.
    None dönerse normal API akışına devam edilir.
    """
    msg = message.strip()
    # Hem orijinal hem normalize edilmiş sorguyu dene
    msg_norm = _normalize_query(msg)
    def _match(pattern: "_re.Pattern[str]", text: str) -> bool:
        return bool(pattern.search(text) or pattern.search(msg_norm))

    try:
        from .time_sync import format_datetime_tr, get_current_datetime
        now = get_current_datetime()

        if _match(_BOTH_PATTERNS, msg) or (
            _match(_DATE_PATTERNS, msg) and _match(_TIME_PATTERNS, msg)
        ):
            return format_datetime_tr(now)

        if _match(_DATE_PATTERNS, msg):
            from .time_sync import _TR_WEEKDAYS, _TR_MONTHS
            return (
                f"{_TR_WEEKDAYS[now.weekday()]}, "
                f"{now.day} {_TR_MONTHS[now.month]} {now.year}"
            )

        if _match(_TIME_PATTERNS, msg):
            return now.strftime("%H:%M")

    except Exception:
        pass

    if _match(_WEATHER_PATTERNS, msg):
        city = _extract_city(msg)
        return _fetch_weather(city)

    return None

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
        # Tarih/saat → anında yerel yanıt (blocking I/O yok, senkron olabilir)
        if not _WEATHER_PATTERNS.search(message):
            local_reply = _try_local_answer(message)
            if local_reply is not None:
                self.query_one("#chat_log", RichLog).write(
                    f"[bold cyan]Nasrî:[/bold cyan] {local_reply}"
                )
                self.query_one("#chat_input", Input).focus()
                return
        # Hava durumu veya LLM soruları → thread'de çalıştır
        self._stream_message(message)

    @work(thread=True)
    def _stream_message(self, message: str) -> None:
        """SSE stream ile Ollama'dan yanıt alır; hava durumu sorularını yerel çözer."""
        self.call_from_thread(self._set_responding, True)

        # Hava durumu → wttr.in'den çek, LLM'ye gitme
        if _WEATHER_PATTERNS.search(message):
            city = _extract_city(message)
            self.call_from_thread(
                self._update_streaming_reply, f"{city} için hava durumu alınıyor..."
            )
            result = _fetch_weather(city)
            self.call_from_thread(self._finish_reply, result)
            return

        state = _load_state()
        port = state.get("api_port", "8000")
        url = f"http://localhost:{port}/chat/stream"

        chunks: list[str] = []
        error: str | None = None

        # ConnectError durumunda kısa süreli yeniden deneme
        for attempt in range(3):
            chunks = []
            error = None
            try:
                timeout = httpx.Timeout(connect=5.0, read=45.0, write=5.0, pool=5.0)
                with httpx.Client(timeout=timeout) as client:
                    with client.stream(
                        "POST",
                        url,
                        json={"message": message, "session_id": _SESSION_ID},
                    ) as resp:
                        if resp.status_code != 200:
                            error = f"Sunucu hatası ({resp.status_code})."
                        else:
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
                                    if len(chunks) % 5 == 0:
                                        self.call_from_thread(
                                            self._update_streaming_reply, "".join(chunks)
                                        )
                break  # başarılı — döngüden çık
            except httpx.ConnectError:
                if attempt < 2:
                    import time
                    self.call_from_thread(
                        self._update_streaming_reply,
                        f"Servis bekleniyor... ({attempt + 1}/3)"
                    )
                    time.sleep(3)
                    continue
                error = (
                    "Nasrî API servisine bağlanılamadı.\n"
                    "Kontrol: nasri /status  |  Başlat: nasri start"
                )
            except httpx.ReadTimeout:
                error = "Zaman aşımı (45s) — Ollama yanıt vermedi. Model yüklü mü?"
                break
            except Exception as exc:
                error = f"Bağlantı hatası: {exc}"
                break

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
    if not _TEXTUAL_OK:
        print("'textual' paketi eksik. Kurmak için:")
        print("  pip install 'textual>=0.60.0'")
        return 1
    NasriApp().run()
    return 0
