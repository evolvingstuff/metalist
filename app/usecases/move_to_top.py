from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.services.snapshot import resolve_search_scope
from app.services.store import store
from app.services.sync import generate_new_uuid
from app.services.undo_state import record_move
from app.usecases.base import QueryCommand
from app.usecases.move import _assert_neighbors, _neighbors, apply_move


def _resolve_search_root_ids(note_id: str, search_query: Optional[str]) -> List[str]:
    if search_query is not None and not isinstance(search_query, str):
        raise TypeError(f"search_query must be a string or None, got {type(search_query)}")

    if not isinstance(search_query, str) or search_query.strip() == "":
        root_ids = store.children(None)
        if note_id not in root_ids:
            raise RuntimeError(
                "Integrity failure: move-to-top root missing from root list: "
                f"note_id={note_id}"
            )
        return root_ids

    search_scope = resolve_search_scope(
        search=search_query,
        editing_note_id=None,
    )
    root_ids = search_scope.search_root_ids_ordered
    if root_ids is None:
        raise RuntimeError("Search scope for move-to-top roots must provide ordered root ids")
    if note_id not in root_ids:
        raise RuntimeError(
            "Integrity failure: move-to-top root missing from visible search roots: "
            f"note_id={note_id} search_query={search_query!r}"
        )
    return root_ids


def _resolve_destination(note_id: str, parent_id: Optional[str], search_query: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if parent_id is not None:
        sibling_ids = store.children(parent_id)
        if note_id not in sibling_ids:
            raise RuntimeError(
                "Integrity failure: move-to-top target missing from siblings list: "
                f"note_id={note_id} parent_id={parent_id}"
            )
        first_id = sibling_ids[0]
        if first_id == note_id:
            return None, None
        return None, first_id

    visible_root_ids = _resolve_search_root_ids(note_id, search_query)
    first_visible_root_id = visible_root_ids[0]
    if first_visible_root_id == note_id:
        return None, None

    first_parent_id, first_prev_id, _ = _neighbors(first_visible_root_id)
    if first_parent_id is not None:
        raise RuntimeError(
            "Integrity failure: expected visible search root to be a root note: "
            f"note_id={first_visible_root_id} parent_id={first_parent_id}"
        )
    return first_prev_id, first_visible_root_id


@dataclass
class CmdMoveToTop(QueryCommand):
    note_id: str
    search_query: Optional[str]
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdMoveToTop(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        record = store.get(self.note_id)
        parent_id = record.parent_id
        dest_prev, dest_next = _resolve_destination(self.note_id, parent_id, self.search_query)
        if dest_next is None:
            return {"status": "noop"}

        before_parent, before_prev, before_next = _neighbors(self.note_id)
        if not isinstance(record.tags, str):
            raise RuntimeError(f"Note tags must be a string | note_id={self.note_id}")
        before_tags = record.tags
        after_tags = record.tags

        dest_parent = parent_id

        apply_move(self.note_id, dest_parent, dest_prev, dest_next)
        _assert_neighbors(self.note_id, dest_parent, dest_prev, dest_next)

        record_move(
            self.client_id,
            self.undo_context,
            self.note_id,
            before_parent=before_parent,
            before_prev=before_prev,
            before_next=before_next,
            before_tags=before_tags,
            after_parent=dest_parent,
            after_prev=dest_prev,
            after_next=dest_next,
            after_tags=after_tags,
            viewport=self.viewport,
        )

        update_uuid = generate_new_uuid()
        return {"status": "moved", "updateUUID": update_uuid}
