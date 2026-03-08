from __future__ import annotations

import asyncio
from contextlib import suppress

from app.services.maintenance import run_maintenance_if_due


_task: asyncio.Task | None = None


async def _loop() -> None:
    while True:
        try:
            await run_maintenance_if_due(trigger="schedule")
        except Exception:
            # Worker hatası uygulamayı düşürmemeli.
            pass
        await asyncio.sleep(900)


def start_maintenance_worker() -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())


async def stop_maintenance_worker() -> None:
    global _task
    if not _task:
        return
    _task.cancel()
    with suppress(asyncio.CancelledError):
        await _task
    _task = None
