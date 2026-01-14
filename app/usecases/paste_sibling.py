from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import uuid

from app.usecases.base import QueryCommand
from app.services.store import store, NodeRecord
from app.services.search_index import search_index, extract_tags_for_search
from app.services.search_query import parse_search_query
from app.services.search_text import build_searchable_text_casefold
from app.services.sync import get_clipboard, generate_new_uuid
from app.usecases.create_note import apply_insert_note
from app.usecases.delete_subtree import _collect_subtree_ids
from app.services.undo_state import record_paste


def _compute_inherited_non_meta_tag_terms(parent_id: Optional[str]) -> set[str]:
    inherited: set[str] = set()
    current_id = parent_id
    while current_id is not None:
        ancestor = store.get(current_id)
        for term in extract_tags_for_search(ancestor.tags):
            if term.startswith("@"):  # meta tags do not inherit
                continue
            inherited.add(term)
        current_id = ancestor.parent_id
    return inherited


def _note_has_positive_matching_ancestor(parent_id: Optional[str], positive_matches: set[str]) -> bool:
    current_id = parent_id
    while current_id is not None:
        if current_id in positive_matches:
            return True
        current_id = store.get(current_id).parent_id
    return False


def _ensure_tags_match_search_query(
    *,
    parent_id: Optional[str],
    content: str,
    tags: str,
    search_query: str,
) -> str:
    if not isinstance(content, str):
        raise TypeError(f"content must be a string, got {type(content)}")
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")
    if not isinstance(search_query, str):
        raise TypeError(f"search_query must be a string, got {type(search_query)}")

    parsed = parse_search_query(search_query)
    if not parsed.required_tags and not parsed.required_text:
        return tags

    inherited_non_meta = _compute_inherited_non_meta_tag_terms(parent_id)
    explicit_terms = extract_tags_for_search(tags)

    additions: list[str] = []
    for term in sorted(parsed.required_tags):
        if term.startswith("@"):
            if term in explicit_terms:
                continue
            additions.append(term)
            continue
        if term in inherited_non_meta or term in explicit_terms:
            continue
        additions.append(term)

    next_tags = tags.strip()
    if additions:
        if next_tags == "":
            next_tags = " ".join(additions)
        else:
            next_tags = f"{next_tags} {' '.join(additions)}"

    if not parsed.required_text:
        return next_tags

    searchable = build_searchable_text_casefold(content, next_tags)
    missing_phrases: list[str] = []
    for phrase in parsed.required_text:
        if phrase.casefold() in searchable:
            continue
        missing_phrases.append(phrase)

    if not missing_phrases:
        return next_tags

    comment_tokens: list[str] = []
    for phrase in missing_phrases:
        if not isinstance(phrase, str):
            raise TypeError(f"search phrase must be a string, got {type(phrase)}")
        if "/*" in phrase or "*/" in phrase:
            continue
        comment_tokens.append(f"/*{phrase}*/")

    if not comment_tokens:
        return next_tags

    suffix = " ".join(comment_tokens)
    if next_tags == "":
        return suffix
    return f"{next_tags} {suffix}"


def _insert_cloned_subtree_at(
    snapshot: List[dict],
    dest_parent: Optional[str],
    dest_prev: Optional[str],
    token: str,
    *,
    search_query: str | None,
) -> str:
    if not isinstance(snapshot, list) or not snapshot:
        raise ValueError("Clipboard snapshot must be a non-empty list")
    for entry in snapshot:
        if not isinstance(entry, dict):
            raise ValueError("Clipboard snapshot entries must be objects")

    # Map old->new ids
    id_map: Dict[str, str] = {}
    # Track last inserted child per parent
    last_per_parent: Dict[Optional[str], Optional[str]] = {}
    last_per_parent[dest_parent] = dest_prev

    new_root_id: Optional[str] = None
    snapshot_ids: set[str] = set()
    positive_matches: set[str] = set()
    should_force_root_match = False
    if search_query is not None:
        if not isinstance(search_query, str):
            raise TypeError(f"search_query must be a string or None, got {type(search_query)}")
        if search_query.strip() != "":
            positive_matches = set(search_index.query_note_ids(search_query))
            if not _note_has_positive_matching_ancestor(dest_parent, positive_matches):
                should_force_root_match = True

    for rec in snapshot:
        if "id" not in rec:
            raise ValueError("Clipboard snapshot missing required key: id")
        note_id = rec["id"]
        if not isinstance(note_id, str) or not note_id:
            raise ValueError("Clipboard snapshot id must be a non-empty string")
        snapshot_ids.add(note_id)

    for rec in snapshot:
        old_id = rec["id"]
        new_id = str(uuid.uuid4())
        id_map[old_id] = new_id

        if "parent_id" not in rec:
            raise ValueError("Clipboard snapshot missing required key: parent_id")
        old_parent = rec["parent_id"]
        if old_parent is None or old_parent not in snapshot_ids:
            new_parent = dest_parent
        elif old_parent in id_map:
            new_parent = id_map[old_parent]
        else:
            raise RuntimeError(
                f"Clipboard snapshot missing parent {old_parent} for node {old_id}"
            )

        if new_parent not in last_per_parent:
            last_per_parent[new_parent] = None
        prev_id = last_per_parent[new_parent]
        # Compute next from current store state
        if prev_id is None:
            children = store.children(new_parent)
            next_id = None
            if children:
                next_id = children[0]
        else:
            links = store._links.get(new_parent)  # type: ignore[attr-defined]
            if links is None:
                raise RuntimeError(f"Missing link scope for parent_id={new_parent}")
            prev_link = links.get(prev_id)
            if prev_link is None:
                raise RuntimeError(f"Missing prev_id={prev_id} in links for parent_id={new_parent}")
            next_id = prev_link.get('next')

        if "content" not in rec:
            raise ValueError("Clipboard snapshot missing required key: content")
        content = rec["content"]
        if not isinstance(content, str):
            raise ValueError("Clipboard snapshot content must be a string")

        if "tags" not in rec:
            raise ValueError("Clipboard snapshot missing required key: tags")
        tags = rec["tags"]
        if not isinstance(tags, str):
            raise ValueError("Clipboard snapshot tags must be a string")

        is_new_root = new_root_id is None and new_parent == dest_parent
        if is_new_root and should_force_root_match:
            tags = _ensure_tags_match_search_query(
                parent_id=dest_parent,
                content=content,
                tags=tags,
                search_query=search_query,
            )

        apply_insert_note(
            new_id,
            new_parent,
            prev_id,
            next_id,
            token,
            content=content,
            tags=tags,
        )

        if new_id not in last_per_parent:
            last_per_parent[new_id] = None

        last_per_parent[new_parent] = new_id
        if new_root_id is None and new_parent == dest_parent:
            new_root_id = new_id

    if new_root_id is None:
        raise RuntimeError("Clipboard paste did not produce a new root id")
    return new_root_id


@dataclass
class CmdPasteSibling(QueryCommand):
    target_note_id: str
    search_query: str | None
    token: str
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdPasteSibling(target={self.target_note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        snapshot = get_clipboard(self.client_id)
        if not snapshot:
            raise RuntimeError("Clipboard empty")

        target = store.get(self.target_note_id)
        siblings = store.children(target.parent_id)
        if target.id not in siblings:
            raise RuntimeError(
                "Integrity failure: paste target missing from siblings list: "
                f"note_id={target.id} parent_id={target.parent_id}"
            )
        prev_id = target.id
        new_root_id = _insert_cloned_subtree_at(
            snapshot,
            target.parent_id,
            prev_id,
            self.token,
            search_query=self.search_query,
        )

        # Record for undo: as paste_subtree (undo deletes, redo restores)
        new_ids = _collect_subtree_ids(new_root_id)
        records: List[NodeRecord] = [store.get(nid) for nid in new_ids]
        record_paste(self.client_id, self.undo_context, records, viewport=self.viewport)

        return {"status": "pasted", "id": new_root_id, "updateUUID": generate_new_uuid()}
