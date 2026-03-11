"""
tui.py — `nasri watch` terminal bildirim paneli.

Gereksinim: rich (requirements.txt'te tanımlı)
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from .config import local_version, state_file
from .notifications import list_all, mark_all_read

_KIND_COLOR = {
    "update": "bold green",
    "info": "cyan",
    "action": "bold yellow",
    "error": "bold red",
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


def _fmt_ts(iso: str) -> str:
    try:
        return dt.datetime.fromisoformat(iso).strftime("%m-%d %H:%M")
    except Exception:
        return iso[:16]


def _build(console: object) -> object:
    from rich import box
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    state = _load_state()
    notifications = list_all()
    unread = [n for n in notifications if not n.get("read")]

    status = state.get("status", "unknown")
    last_update = state.get("last_update_result", "n/a")
    api_port = state.get("api_port", "n/a")
    version = local_version()
    status_color = "green" if status == "running" else "red"

    header = Text()
    header.append("Nasrî ", style="bold")
    header.append(f"v{version}  ", style="dim")
    header.append(f"● {status}", style=status_color)
    header.append(f"  port:{api_port}", style="dim")
    header.append(f"  güncelleme:{last_update}", style="dim")

    table = Table(
        title=f"Bildirimler — {len(unread)} okunmamış / {len(notifications)} toplam",
        show_header=True,
        header_style="bold",
        border_style="dim",
        box=box.SIMPLE,
        expand=True,
    )
    table.add_column("", width=2, no_wrap=True)
    table.add_column("Tür", width=8, no_wrap=True)
    table.add_column("Başlık", width=26)
    table.add_column("Mesaj")
    table.add_column("Zaman", width=12, no_wrap=True)

    for n in notifications[:25]:
        kind = n.get("kind", "info")
        color = _KIND_COLOR.get(kind, "white")
        icon = _KIND_ICON.get(kind, " ")
        dot = "[bold yellow]•[/bold yellow]" if not n.get("read") else " "
        table.add_row(
            dot,
            f"[{color}]{icon} {kind}[/{color}]",
            f"[{color}]{n.get('title', '')}[/{color}]",
            n.get("message", ""),
            f"[dim]{_fmt_ts(n.get('timestamp', ''))}[/dim]",
        )

    if not notifications:
        table.add_row("", "[dim]—[/dim]", "[dim]Henüz bildirim yok[/dim]", "", "")

    footer = Text("Çıkmak için Ctrl+C  •  Çıkışta tümü okundu sayılır", style="dim", justify="center")

    return Group(Panel(header, border_style="dim"), table, footer)


def run_watch() -> int:
    try:
        from rich.console import Console
        from rich.live import Live
    except ImportError:
        print("'rich' paketi eksik. Kurmak için: pip install rich")
        return 1

    console = Console()
    console.print("[dim]Nasrî bildirim paneli — Ctrl+C ile çık[/dim]\n")

    try:
        with Live(_build(console), console=console, refresh_per_second=1, screen=False) as live:
            while True:
                time.sleep(3)
                live.update(_build(console))
    except KeyboardInterrupt:
        pass

    mark_all_read()
    console.print("\n[dim]Tüm bildirimler okundu olarak işaretlendi.[/dim]")
    return 0
