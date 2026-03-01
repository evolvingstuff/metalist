from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict

from app.usecases.base import QueryCommand
from app.usecases.delete_subtree import _snapshot_subtree, apply_delete_subtree
from app.usecases.update_content import apply_update_content
from app.services.content_formatting import _tokenize_tag_bar
from app.services.store import store
from app.services.sync import generate_new_uuid
from app.services.undo_state import record_join_next


def _merge_note_content_html(current_content: str, next_content: str) -> str:
    if not isinstance(current_content, str):
        raise TypeError("current_content must be a string")
    if not isinstance(next_content, str):
        raise TypeError("next_content must be a string")

    left = current_content.strip()
    right = next_content.strip()

    if left == "":
        return right
    if right == "":
        return left

    ends_with_line_boundary = re.search(r"<br\s*/?>\s*$", left, flags=re.IGNORECASE) is not None
    if not ends_with_line_boundary:
        ends_with_line_boundary = re.search(
            r"</(?:div|p|li|h[1-6]|pre|blockquote|ul|ol|table|tr|td|th|section|article|header|footer)>\s*$",
            left,
            flags=re.IGNORECASE,
        ) is not None
    starts_with_line_boundary = re.search(r"^\s*<br\s*/?>", right, flags=re.IGNORECASE) is not None
    if not starts_with_line_boundary:
        starts_with_line_boundary = re.search(
            r"^\s*<(?:div|p|li|h[1-6]|pre|blockquote|ul|ol|table|tr|td|th|section|article|header|footer)\b",
            right,
            flags=re.IGNORECASE,
        ) is not None
    if ends_with_line_boundary or starts_with_line_boundary:
        return f"{left}{right}"
    return f"{left}<br>{right}"


def _merge_note_tags(current_tags: str, next_tags: str) -> str:
    if not isinstance(current_tags, str):
        raise TypeError("current_tags must be a string")
    if not isinstance(next_tags, str):
        raise TypeError("next_tags must be a string")

    merged: list[str] = []
    seen: set[str] = set()
    for source in (current_tags, next_tags):
        for token in _tokenize_tag_bar(source):
            dedupe_key = token.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            merged.append(token)
    return " ".join(merged)


@dataclass
class CmdJoinNextSibling(QueryCommand):
    note_id: str
    token: str
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdJoinNextSibling(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        current_record = store.get(self.note_id)
        siblings = store.children(current_record.parent_id)
        if self.note_id not in siblings:
            raise RuntimeError(
                "Integrity failure: join target missing from siblings list: "
                f"note_id={self.note_id} parent_id={current_record.parent_id}"
            )

        current_index = siblings.index(self.note_id)
        if current_index + 1 >= len(siblings):
            return {"status": "noop", "id": self.note_id}

        next_note_id = siblings[current_index + 1]
        next_children = store.children(next_note_id)
        if len(next_children) > 0:
            # Safety guard: avoid destructive subtree loss on join.
            return {"status": "noop", "id": self.note_id}

        next_record = store.get(next_note_id)

        if not isinstance(current_record.content, str):
            raise RuntimeError(f"Current note content must be a string | note_id={self.note_id}")
        if not isinstance(current_record.tags, str):
            raise RuntimeError(f"Current note tags must be a string | note_id={self.note_id}")
        if not isinstance(next_record.content, str):
            raise RuntimeError(f"Next note content must be a string | note_id={next_note_id}")
        if not isinstance(next_record.tags, str):
            raise RuntimeError(f"Next note tags must be a string | note_id={next_note_id}")

        before_content = current_record.content
        before_tags = current_record.tags
        after_content = _merge_note_content_html(before_content, next_record.content)
        after_tags = _merge_note_tags(before_tags, next_record.tags)

        deleted_records = _snapshot_subtree(next_note_id)
        apply_update_content(self.note_id, after_content, after_tags, self.token)
        apply_delete_subtree(next_note_id)

        record_join_next(
            self.client_id,
            self.undo_context,
            note_id=self.note_id,
            before_content=before_content,
            before_tags=before_tags,
            after_content=after_content,
            after_tags=after_tags,
            deleted_records=deleted_records,
            viewport=self.viewport,
        )

        update_uuid = generate_new_uuid()
        return {
            "status": "joined",
            "id": self.note_id,
            "removedId": next_note_id,
            "updateUUID": update_uuid,
        }
