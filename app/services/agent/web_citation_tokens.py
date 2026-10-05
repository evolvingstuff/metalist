"""Translate the model's short web citation tokens back to full evidence tokens.

The model cites web pages and their links as ``[[web:N]]``: short per-session
numbers it copies reliably, unlike 36-character ids. Everything after the model
(storage, rendering, references) keeps the full ``[[web:<evidence id>]]`` form, so
the agent loop translates the answer as it streams. A token can be split across
stream chunks, so a trailing fragment that could still become a token is held
back until the next chunk or the end of the turn.
"""

from __future__ import annotations

import re
from collections.abc import Callable


_SHORT_TOKEN_RE = re.compile(r"\[\[web:(\d+)\]\]")
# A tail that could still grow into a short token: "[", "[[", "[[w" … "[[web:12", "[[web:12]".
_PARTIAL_TAIL_RE = re.compile(r"\[(?:\[(?:w(?:e(?:b(?::(?:\d+\]?)?)?)?)?)?)?$")


class ShortWebTokenTranslator:
    def __init__(self, *, evidence_ids_by_number: Callable[[], dict[int, str]]) -> None:
        self._evidence_ids_by_number = evidence_ids_by_number
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
            number = int(match.group(1))
            # An unknown number is dropped, as the renderer drops unknown evidence ids.
            if number not in evidence_ids:
                return ""
            return f"[[web:{evidence_ids[number]}]]"

        return _SHORT_TOKEN_RE.sub(replace, text)
