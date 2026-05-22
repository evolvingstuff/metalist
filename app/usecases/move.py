from __future__ import annotations

from dataclasses import dataclass
import os
import logging
from typing import Dict, Optional, Tuple

from app.usecases.base import QueryCommand
from app.services.store import store
from app.services.sync import generate_new_uuid

from app.db.session import begin_writer
from app.db.notes_sql import update_links_preserving_updated_at as db_update_links_preserving_updated_at


def _neighbors(note_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    rec = store.get(note_id)
    parent_id = rec.parent_id
    links = store._links.get(parent_id)  # type: ignore[attr-defined]
    if links is None:
        raise RuntimeError(f"Missing link scope for parent_id={parent_id}")
    cur = links.get(note_id)
    if cur is None:
        raise RuntimeError(f"Missing note_id={note_id} in links for parent_id={parent_id}")
    if 'prev' not in cur or 'next' not in cur:
        raise RuntimeError(f"Malformed link entry for note_id={note_id} parent_id={parent_id}: {cur}")
    return parent_id, cur['prev'], cur['next']


def _assert_neighbors(note_id: str, exp_parent: Optional[str], exp_prev: Optional[str], exp_next: Optional[str]) -> None:
    parent_id, prev_id, next_id = _neighbors(note_id)
    if parent_id != exp_parent or prev_id != exp_prev or next_id != exp_next:
        logging.error(
            "FATAL: move invariant failed for %s | expected parent=%s prev=%s next=%s | actual parent=%s prev=%s next=%s",
            note_id, exp_parent, exp_prev, exp_next, parent_id, prev_id, next_id,
        )
        os._exit(1)


def apply_move(note_id: str, new_parent_id: Optional[str], prev_id: Optional[str], next_id: Optional[str]) -> None:
    old_parent, old_prev, old_next = _neighbors(note_id)
    with begin_writer() as connection:
        if old_prev:
            db_update_links_preserving_updated_at(connection, old_prev, next_id=old_next)
        if old_next:
            db_update_links_preserving_updated_at(connection, old_next, prev_id=old_prev)

        db_update_links_preserving_updated_at(connection, note_id, parent_id=new_parent_id, prev_id=prev_id, next_id=next_id)
        if prev_id:
            db_update_links_preserving_updated_at(connection, prev_id, next_id=note_id)
        if next_id:
            db_update_links_preserving_updated_at(connection, next_id, prev_id=note_id)

    store.move_note(note_id, new_parent_id, prev_id)


@dataclass
class CmdMove(QueryCommand):
    note_id: str
    sibling_id: Optional[str]
    position: Optional[str]  # 'BEFORE' or 'AFTER'
    new_parent_id: Optional[str]
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdMove(note={self.note_id}, sib={self.sibling_id}, pos={self.position}, parent={self.new_parent_id})"

    def execute(self) -> Dict[str, str]:
        # Validate inputs strictly (move up/down expects sibling + position)
        if not self.sibling_id or not (self.position or '').strip():
            print(f"FATAL: move requires sibling_id and position | got sibling_id={self.sibling_id} position={self.position}")
            os._exit(1)

        # Determine destination
        if self.sibling_id:
            sib = store.get(self.sibling_id)
            if self.new_parent_id is not None:
                dest_parent = self.new_parent_id
            else:
                dest_parent = sib.parent_id
            links = store._links.get(dest_parent)  # type: ignore[attr-defined]
            if links is None:
                raise RuntimeError(f"Missing link scope for parent_id={dest_parent}")
            sib_link = links.get(self.sibling_id)
            if sib_link is None:
                raise RuntimeError(f"Missing note_id={self.sibling_id} in links for parent_id={dest_parent}")
            if 'prev' not in sib_link or 'next' not in sib_link:
                raise RuntimeError(
                    f"Malformed link entry for note_id={self.sibling_id} parent_id={dest_parent}: {sib_link}"
                )
            if (self.position or '').upper() == 'BEFORE':
                next_id = self.sibling_id
                prev_id = sib_link['prev']
            else:
                prev_id = self.sibling_id
                next_id = sib_link['next']
        else:  # Should not happen for up/down; fail fast
            print("FATAL: move without sibling_id not supported in this flow")
            os._exit(1)

        # Record move for undo
        old_parent, old_prev, old_next = _neighbors(self.note_id)
        record = store.get(self.note_id)
        if not isinstance(record.tags, str):
            raise RuntimeError(f"Note tags must be a string | note_id={self.note_id}")
        before_tags = record.tags
        after_tags = record.tags

        apply_move(self.note_id, dest_parent, prev_id, next_id)
        _assert_neighbors(self.note_id, dest_parent, prev_id, next_id)

        from app.services.undo_state import record_move
        record_move(
            self.client_id,
            self.undo_context,
            self.note_id,
            before_parent=old_parent,
            before_prev=old_prev,
            before_next=old_next,
            before_tags=before_tags,
            after_parent=dest_parent,
            after_prev=prev_id,
            after_next=next_id,
            after_tags=after_tags,
            viewport=self.viewport,
        )

        update_uuid = generate_new_uuid()
        return {"status": "moved", "updateUUID": update_uuid}
