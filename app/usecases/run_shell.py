from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from app.usecases.base import QueryCommand
from app.services.content_formatting import _extract_plain_text, _find_first_renderer_tag
from app.services.shell_session_service import shell_session_service
from app.services.store import store


def _invalid_shell_response(*, error_message: str) -> Dict[str, object]:
    if not isinstance(error_message, str) or error_message == "":
        raise TypeError("error_message must be a non-empty string")
    return {
        "runId": "",
        "status": "error",
        "exitCode": -1,
        "stdout": "",
        "stderr": "",
        "durationMs": 0,
        "errorMessage": error_message,
        "acceptsInput": False,
    }


@dataclass
class CmdRunShellStart(QueryCommand):
    note_id: str
    timeout_seconds: int

    def describe(self) -> str:
        return f"CmdRunShellStart(note={self.note_id})"

    def execute(self) -> Dict[str, object]:
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds < 0:
            raise TypeError("timeout_seconds must be a non-negative integer")

        record = store.get(self.note_id)
        if _find_first_renderer_tag(record.tags) != "shell":
            return _invalid_shell_response(error_message="Note is not tagged @shell")
        script_text = _extract_plain_text(record.content)
        if script_text.strip() == "":
            return _invalid_shell_response(error_message="Shell script is empty")
        return shell_session_service.start_run(
            note_id=self.note_id,
            script_text=script_text,
            timeout_seconds=self.timeout_seconds,
        )

@dataclass
class CmdRunShellStatus(QueryCommand):
    note_id: str
    run_id: str

    def describe(self) -> str:
        return f"CmdRunShellStatus(note={self.note_id}, run={self.run_id})"

    def execute(self) -> Dict[str, object]:
        return shell_session_service.get_snapshot(
            note_id=self.note_id,
            run_id=self.run_id,
        )


@dataclass
class CmdRunShellInput(QueryCommand):
    note_id: str
    run_id: str
    text: str
    append_newline: bool

    def describe(self) -> str:
        return f"CmdRunShellInput(note={self.note_id}, run={self.run_id})"

    def execute(self) -> Dict[str, object]:
        return shell_session_service.write_input(
            note_id=self.note_id,
            run_id=self.run_id,
            text=self.text,
            append_newline=self.append_newline,
        )
