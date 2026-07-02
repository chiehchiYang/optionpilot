"""A tiny thread-local progress channel so slow, deeply-nested work (e.g. a ThetaData fetch) can
report LIVE status up to whatever drives it (the agent loop's on_event -> the GUI/CLI), without
threading a callback through every layer.

Set a sink for the current thread with `progress_to(sink)`; deep code calls `report(msg)`. With no
sink set (or in another thread), report() is a no-op. The agent loop sets the sink around a run, so
tool / data-source code running in that same thread reaches it.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable

_local = threading.local()


def report(message: str) -> None:
    """Emit a progress message to the current thread's sink, if one is set (else no-op)."""
    sink: Callable[[str], None] | None = getattr(_local, "sink", None)
    if sink is not None:
        try:
            sink(message)
        except Exception:  # noqa: BLE001 - progress must never break the actual work
            pass


@contextlib.contextmanager
def progress_to(sink: Callable[[str], None]):
    """Route report() calls on THIS thread to `sink` for the duration of the block."""
    prev = getattr(_local, "sink", None)
    _local.sink = sink
    try:
        yield
    finally:
        _local.sink = prev
