"""The notes the experiment learns from, as plain in-memory data.

A Corpus is built either from a namespace snapshot (extract.py) or from the
synthetic generator (synthetic.py). It never touches a database itself and is
never written to disk: it holds the user's decrypted notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CorpusNote:
    note_id: str
    parent_id: str | None
    content_html: str
    plain_text: str
    # The tag bar as written, e.g. "ssm papers @todo".
    tags: str
    # Non-meta explicit tags in the order written: the targets.
    explicit_tags: tuple[str, ...]
    # Meta (@) tags in the order written: always visible, never targets.
    meta_tags: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True)
class Corpus:
    notes: dict[str, CorpusNote]
    # Children in display order; roots under None.
    children: dict[str | None, tuple[str, ...]]
    rules_text: str

    def __post_init__(self) -> None:
        listed = [note_id for child_ids in self.children.values() for note_id in child_ids]
        assert len(listed) == len(set(listed)), "a note is listed under two parents"
        assert set(listed) == set(self.notes), "children must list every note exactly once"
        for parent_id, child_ids in self.children.items():
            for child_id in child_ids:
                assert self.notes[child_id].parent_id == parent_id, f"note {child_id} listed under the wrong parent"

    def ancestors(self, note_id: str) -> list[str]:
        """Parent first, root last."""
        chain: list[str] = []
        parent_id = self.notes[note_id].parent_id
        while parent_id is not None:
            chain.append(parent_id)
            parent_id = self.notes[parent_id].parent_id
        return chain

    def siblings(self, note_id: str) -> tuple[str, ...]:
        return tuple(sibling for sibling in self.children[self.notes[note_id].parent_id] if sibling != note_id)

    def child_ids(self, note_id: str) -> tuple[str, ...]:
        if note_id not in self.children:
            return ()
        return self.children[note_id]

    def descendants(self, note_id: str) -> list[str]:
        found: list[str] = []
        pending = list(self.child_ids(note_id))
        while pending:
            current = pending.pop()
            found.append(current)
            pending.extend(self.child_ids(current))
        return found
