from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Any

from app.usecases.base import QueryCommand
from app.services.store import store, NodeRecord
from app.services.search_index import extract_tags_for_search
from app.services.sync import set_clipboard, generate_new_uuid
from app.models.utils import (
    render_note_data_read_only,
    note_data_to_html,
    note_data_to_plain_text,
)


def snapshot_subtree_preorder(root_id: str) -> List[NodeRecord]:
    result: List[NodeRecord] = []
    stack: List[str] = [root_id]
    while stack:
        nid = stack.pop()
        rec = store.get(nid)
        result.append(rec)
        children = list(reversed(store.children(nid)))
        for cid in children:
            stack.append(cid)
    return result


def _build_serialized_tree(root_id: str) -> Dict[str, Any]:
    """Build a pure data representation of a note subtree for rendering.

    The shape matches v1's clipboard serialization used by
    render_note_data_read_only/note_data_to_html/plain_text:
      { content: str, children: [ ...same shape... ] }
    """
    rec = store.get(root_id)
    assert isinstance(rec.content, str)
    assert isinstance(rec.tags, str)
    children = store.children(root_id)
    return {
        "content": rec.content,
        "tags": rec.tags,
        "children": [_build_serialized_tree(cid) for cid in children],
    }


def _compute_inherited_non_meta_tag_terms(note_id: str) -> tuple[str, ...]:
    root = store.get(note_id)
    assert isinstance(root.tags, str)
    inherited_non_meta: set[str] = set()
    current_id = root.parent_id
    while current_id is not None:
        ancestor = store.get(current_id)
        assert isinstance(ancestor.tags, str)
        for term in extract_tags_for_search(ancestor.tags):
            if term.startswith("@"):  # meta tags do not inherit
                continue
            inherited_non_meta.add(term)
        current_id = ancestor.parent_id
    return tuple(sorted(inherited_non_meta))


@dataclass
class CmdCopyNote(QueryCommand):
    note_id: str
    client_id: str

    def describe(self) -> str:
        return f"CmdCopyNote(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, Any]:
        inherited_non_meta_tag_terms = _compute_inherited_non_meta_tag_terms(self.note_id)

        # Snapshot for server-side clipboard (structure + plaintext content)
        records = snapshot_subtree_preorder(self.note_id)
        payload = [
            {
                "id": r.id,
                "parent_id": r.parent_id,
                "prev_id": r.prev_id,
                "next_id": r.next_id,
                "is_collapsed": bool(r.is_collapsed),
                "content": r.content,
                "tags": r.tags,
                "inherited_non_meta_tag_terms": list(inherited_non_meta_tag_terms) if r.id == self.note_id else [],
            }
            for r in records
        ]
        set_clipboard(self.client_id, payload)

        # Produce rendered HTML + plain text for system clipboard parity with v1
        tree = _build_serialized_tree(self.note_id)
        rendered = render_note_data_read_only(tree)
        html = note_data_to_html(rendered)
        plain_text = note_data_to_plain_text(rendered)

        return {
            "status": "success",
            "html": html,
            "plain_text": plain_text,
            "updateUUID": generate_new_uuid(),
        }
