from __future__ import annotations

from types import TracebackType
import traceback


def traceback_frame_summary(exc_traceback: TracebackType | None) -> list[str]:
    """Describe traceback locations without exception messages or local values."""
    if exc_traceback is None:
        return []
    return [
        f"{frame.filename}:{frame.lineno}:{frame.name}"
        for frame in traceback.extract_tb(exc_traceback)
    ]
