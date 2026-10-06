"""Translate the model's short citation tokens back to full ones as the answer streams.

The model cites web pages and links as ``[[web:N]]`` (numbered per chat session by
the web evidence store) and notes as ``[[nK]]`` (per-run note aliases, see
note_aliases.py): short tokens it copies reliably, unlike 36-character ids.
Everything after the model (storage, rendering, references) keeps the full
``[[web:<evidence id>]]`` and ``[[<note id>]]`` forms. A token can be split across
stream chunks, so a trailing fragment that could still become one is held back until
the next chunk or the end of the turn.
"""

from __future__ import annotations

import re
from collections.abc import Callable


_SHORT_TOKEN_RE = re.compile(r"\[\[(?:web:(?P<web>\d+)|(?P<note>n[1-9]\d*))\]\]")
# A tail that could still grow into a short token: "[", "[[", "[[w" … "[[web:12", "[[n1", "[[n12]".
_PARTIAL_TAIL_RE = re.compile(r"\[(?:\[(?:w(?:e(?:b(?::(?:\d+\]?)?)?)?)?|n(?:\d+\]?)?)?)?$")


class ShortCitationTranslator:
    def __init__(self, *, evidence_ids_by_number: Callable[[], dict[int, str]],
                 note_ids_by_alias: dict[str, str]) -> None:
        self._evidence_ids_by_number = evidence_ids_by_number
        self._note_ids_by_alias = dict(note_ids_by_alias)
        self._pending = ""

    def feed(self, text: str) -> str:
        """Translated text that is safe to show now (possibly empty)."""
        assert isinstance(text, str)
        buffered = self._pending + text
        tail = _PARTIAL_TAIL_RE.search(buffered)
        split_at = len(buffered)
        if tail is not None:
            split_at = tail.start()
        self._pending = buffered[split_at:]
        return self._translate(buffered[:split_at])

    def flush(self) -> str:
        """Everything still held back, at the end of a turn."""
        remaining = self._translate(self._pending)
        self._pending = ""
        return remaining

    def _translate(self, text: str) -> str:
        evidence_ids = self._evidence_ids_by_number()

        def replace(match: re.Match[str]) -> str:
            # An unknown number or alias is dropped, as the renderer drops unknown ids.
            if match.group("web") is not None:
                number = int(match.group("web"))
                if number not in evidence_ids:
                    return ""
                return f"[[web:{evidence_ids[number]}]]"
            alias = match.group("note")
            if alias not in self._note_ids_by_alias:
                return ""
            return f"[[{self._note_ids_by_alias[alias]}]]"

        return _SHORT_TOKEN_RE.sub(replace, text)
