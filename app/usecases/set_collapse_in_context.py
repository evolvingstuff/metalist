from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from app.services.note_store import store as note_store
from app.services.search_index import search_index
from app.services.search_query import parse_search_query
from app.services.store import store
from app.services.sync import generate_new_uuid
from app.services.undo_state import record_collapse
from app.usecases.base import QueryCommand
from app.usecases.collapse import apply_set_collapse_bulk


def _collect_descendants(root_id: str) -> List[str]:
    if not isinstance(root_id, str) or not root_id:
        raise TypeError("root_id must be a non-empty string")
    if not note_store.has_note(root_id):
        raise RuntimeError(f"Unknown root_id: {root_id}")

    results: List[str] = []
    to_visit = [root_id]
    while to_visit:
        current_id = to_visit.pop()
        results.append(current_id)
        for child_id in note_store.get_children(current_id):
            to_visit.append(child_id)
    return results


def _quote_text_term_for_query(phrase: str) -> str:
    if not isinstance(phrase, str):
        raise TypeError(f"search phrase must be a string, got {type(phrase)}")

    if '"' not in phrase:
        escaped = phrase.replace('\\', '\\\\')
        return f'"{escaped}"'

    if "'" not in phrase:
        escaped = phrase.replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    escaped = phrase.replace('\\', '\\\\').replace('\"', '\\"')
    return f'"{escaped}"'


def _include_ancestors(note_ids: Set[str], *, starting_ids: Set[str]) -> None:
    to_visit = list(starting_ids)
    while to_visit:
        current_id = to_visit.pop()
        if not note_store.has_note(current_id):
            continue
        parent_id = note_store.get_note(current_id).parent_id
        if parent_id is None:
            continue
        if parent_id in note_ids:
            continue
        note_ids.add(parent_id)
        to_visit.append(parent_id)


def _include_descendants(note_ids: Set[str], *, starting_ids: Set[str]) -> None:
    to_visit = list(starting_ids)
    while to_visit:
        current_id = to_visit.pop()
        if not note_store.has_note(current_id):
            continue
        for child_id in note_store.get_children(current_id):
            if child_id in note_ids:
                continue
            note_ids.add(child_id)
            to_visit.append(child_id)


def _collect_context_root_ids(search_query: Optional[str]) -> List[str]:
    ordered_root_ids = note_store.get_children(None)

    if search_query is None:
        return list(ordered_root_ids)

    if not isinstance(search_query, str):
        raise TypeError("search_query must be a string or null")

    parsed = parse_search_query(search_query)
    has_terms = False
    if len(parsed.required_tags) > 0:
        has_terms = True
    if len(parsed.forbidden_tags) > 0:
        has_terms = True
    if len(parsed.required_text) > 0:
        has_terms = True
    if len(parsed.forbidden_text) > 0:
        has_terms = True

    if not has_terms:
        return list(ordered_root_ids)

    positively_matched_note_ids = set(search_index.query_note_ids(search_query))
    allowed_note_ids = set(positively_matched_note_ids)

    excluded_note_ids: Set[str] = set()
    for tag in parsed.forbidden_tags:
        excluded_note_ids.update(search_index.query_note_ids(tag))

    for phrase in parsed.forbidden_text:
        excluded_note_ids.update(search_index.query_note_ids(_quote_text_term_for_query(phrase)))

    _include_ancestors(allowed_note_ids, starting_ids=set(allowed_note_ids))
    _include_descendants(allowed_note_ids, starting_ids=set(positively_matched_note_ids))
    if excluded_note_ids:
        allowed_note_ids.difference_update(excluded_note_ids)

    return [root_id for root_id in ordered_root_ids if root_id in allowed_note_ids]


@dataclass
class CmdSetCollapseInContext(QueryCommand):
    search_query: Optional[str]
    collapsed: bool
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        normalized = ""
        if self.search_query is not None:
            normalized = self.search_query
        return f"CmdSetCollapseInContext(search={normalized!r}, collapsed={self.collapsed}, client={self.client_id})"

    def execute(self) -> Dict[str, object]:
        root_ids = _collect_context_root_ids(self.search_query)

        note_ids: List[str] = []
        seen: Set[str] = set()
        for root_id in root_ids:
            for note_id in _collect_descendants(root_id):
                if note_id in seen:
                    continue
                seen.add(note_id)
                note_ids.append(note_id)

        before_by_id: Dict[str, bool] = {}
        note_ids_to_update: List[str] = []

        for note_id in note_ids:
            before = bool(store.get(note_id).is_collapsed)
            if before is bool(self.collapsed):
                continue
            before_by_id[note_id] = before
            note_ids_to_update.append(note_id)

        if note_ids_to_update:
            apply_set_collapse_bulk(note_ids_to_update, bool(self.collapsed))

        updated_count = 0
        for note_id in note_ids_to_update:
            after = bool(store.get(note_id).is_collapsed)
            if after is not bool(self.collapsed):
                print(f"FATAL: context collapse failed for {note_id}")
                os._exit(1)

            record_collapse(
                self.client_id,
                self.undo_context,
                note_id,
                before=before_by_id[note_id],
                after=after,
                viewport=self.viewport,
            )
            updated_count += 1

        status = "unchanged"
        if updated_count > 0:
            status = "updated"

        return {
            "status": status,
            "updatedCount": updated_count,
            "totalCount": len(note_ids),
            "updateUUID": generate_new_uuid(),
        }
