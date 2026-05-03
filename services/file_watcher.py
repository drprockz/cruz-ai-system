"""
FileWatcher — emits SP5 file-watch triggers when monitored files change.

Currently monitors:
  docs/personal/health-journal.md → trigger "filewatch.health_journal"

Architecture:
  - Started from arq_worker.WorkerSettings.on_startup
  - Uses watchdog.Observer (fsevents on macOS, inotify on Linux)
  - On modification, enqueues dispatch_event_to_agent for every agent
    registered against the trigger in EVENT_REGISTRY.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agents.event_driven_agent import EVENT_REGISTRY
# Imported at module level so tests can patch
# `services.file_watcher._get_arq_pool` directly.
from workers.tasks.webhook_tasks import _get_arq_pool

logger = logging.getLogger("cruz.services.file_watcher")


WATCH_MAP = {
    "docs/personal/health-journal.md": "filewatch.health_journal",
}


class _Handler(FileSystemEventHandler):
    """Watchdog handler that forwards modifications of a single file
    onto the asyncio loop for ARQ enqueue."""

    def __init__(
        self,
        path: str,
        trigger: str,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.path = Path(path).resolve()
        self.trigger = trigger
        self.loop = loop

    def on_modified(self, event) -> None:  # noqa: ANN001 — watchdog API
        if Path(event.src_path).resolve() != self.path:
            return
        # Hop back onto the asyncio loop to enqueue
        asyncio.run_coroutine_threadsafe(
            _enqueue_for_trigger(self.trigger),
            self.loop,
        )


async def _enqueue_for_trigger(trigger: str) -> None:
    """For every agent registered against `trigger`, enqueue an
    ARQ dispatch_event_to_agent job."""
    classes = EVENT_REGISTRY.get(trigger, [])
    if not classes:
        return
    pool = await _get_arq_pool()
    for cls in classes:
        await pool.enqueue_job(
            "dispatch_event_to_agent",
            cls.__module__,
            cls.__name__,
            {"trigger": trigger, "data": {"source": "filewatch"}},
        )


_observer: Optional[Observer] = None


def start_file_watcher(loop: asyncio.AbstractEventLoop) -> None:
    """Start the watchdog Observer for all WATCH_MAP entries.

    Idempotent — calling twice is a no-op while an Observer is running.
    """
    global _observer
    if _observer is not None:
        return
    _observer = Observer()
    for path_str, trigger in WATCH_MAP.items():
        p = Path(path_str)
        if not p.exists():
            logger.warning(
                "file_watcher: path missing, will watch parent: %s", p
            )
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
        handler = _Handler(str(p), trigger, loop)
        _observer.schedule(handler, str(p.parent), recursive=False)
    _observer.start()
    logger.info("file_watcher started for: %s", list(WATCH_MAP))


def stop_file_watcher() -> None:
    """Stop the watchdog Observer if running."""
    global _observer
    if _observer is not None:
        _observer.stop()
        _observer.join(timeout=2.0)
        _observer = None
