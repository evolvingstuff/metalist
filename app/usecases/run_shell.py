from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Dict

from app.usecases.base import QueryCommand
from app.services.store import store
from app.services.content_formatting import _extract_plain_text, _find_first_renderer_tag


def _normalize_subprocess_stream(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError("Subprocess stream must be str, bytes, or None")


@dataclass
class CmdRunShell(QueryCommand):
    note_id: str
    timeout_seconds: int

    def describe(self) -> str:
        return f"CmdRunShell(note={self.note_id})"

    def execute(self) -> Dict[str, object]:
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds < 0:
            raise TypeError("timeout_seconds must be a non-negative integer")

        record = store.get(self.note_id)
        if _find_first_renderer_tag(record.tags) != "shell":
            return {
                "status": "error",
                "exitCode": -1,
                "stdout": "",
                "stderr": "",
                "durationMs": 0,
                "errorMessage": "Note is not tagged @shell",
            }
        script_text = _extract_plain_text(record.content)
        if script_text.strip() == "":
            return {
                "status": "error",
                "exitCode": -1,
                "stdout": "",
                "stderr": "",
                "durationMs": 0,
                "errorMessage": "Shell script is empty",
            }

        started_at = time.perf_counter()
        completed = subprocess.run(
            ["/bin/bash", "-lc", script_text],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        stdout_text = _normalize_subprocess_stream(completed.stdout)
        stderr_text = _normalize_subprocess_stream(completed.stderr)
        if not isinstance(completed.returncode, int):
            raise TypeError("Shell returncode must be an integer")

        status = "success"
        error_message = ""
        if completed.returncode != 0:
            status = "error"
            error_message = f"Shell command exited with code {completed.returncode}"

        return {
            "status": status,
            "exitCode": completed.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "durationMs": duration_ms,
            "errorMessage": error_message,
        }
