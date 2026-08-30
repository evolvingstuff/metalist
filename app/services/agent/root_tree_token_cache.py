"""Per-root cache for complete serialized agent evidence token costs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from typing import DefaultDict, Optional, Set

from app.services.agent.evidence_serialization import EvidenceNoteTokenSource
from app.services.agent.evidence_serialization import EvidenceTreeTokenSource
from app.services.agent.evidence_serialization import estimate_cached_root_tree_tokens
from app.services.content_formatting import extract_note_text_for_agent
from app.services.search_index import extract_ordered_tags_for_search


def estimate_result_root_tree_tokens(
    *,
    note_ids: Set[str],
    ordered_root_ids: list[str],
    get_note: Callable[[str], object],
    get_children: Callable[[Optional[str]], list[str]],
    max_note_characters: int,
) -> int:
    if max_note_characters < 1:
        raise ValueError("Result token estimate requires a positive note character limit")
    evidence_notes_by_root_id: DefaultDict[
        str, list[EvidenceNoteTokenSource]
    ] = defaultdict(list)
    structure_ids: set[str] = set()
    root_id_by_structure_id: dict[str, str] = {}
    for note_id in note_ids:
        record = get_note(note_id)
        content_text, is_redacted = extract_note_text_for_agent(
            content_html=record.content,
            tags=record.tags,
        )
        if is_redacted:
            continue
        root_id, path_ids = _root_path(
            note_id=note_id,
            get_note=get_note,
        )
        structure_ids.update(path_ids)
        for structure_id in path_ids:
            root_id_by_structure_id[structure_id] = root_id
        evidence_notes_by_root_id[root_id].append(
            EvidenceNoteTokenSource(
                note_id=note_id,
                content_text=content_text,
                explicit_tag_terms=extract_ordered_tags_for_search(record.tags),
                created_at=_timestamp_text(record, "created_at"),
                updated_at=_timestamp_text(record, "updated_at"),
                character_limit=min(len(content_text), max_note_characters),
            )
        )
    if not evidence_notes_by_root_id:
        return 0
    structure_nodes_by_root_id = _structure_nodes_by_root_id(
        structure_ids=structure_ids,
        root_id_by_structure_id=root_id_by_structure_id,
        get_note=get_note,
        get_children=get_children,
    )
    return sum(
        estimate_cached_root_tree_tokens(
            root_id=root_id,
            evidence_notes=tuple(evidence_notes_by_root_id[root_id]),
            structure_nodes=tuple(structure_nodes_by_root_id[root_id]),
        )
        for root_id in ordered_root_ids
        if root_id in evidence_notes_by_root_id
    )


def warm_all_root_tree_token_costs(
    *,
    note_ids: Set[str],
    ordered_root_ids: list[str],
    get_note: Callable[[str], object],
    get_children: Callable[[Optional[str]], list[str]],
    max_note_characters: int,
) -> int:
    return estimate_result_root_tree_tokens(
        note_ids=note_ids,
        ordered_root_ids=ordered_root_ids,
        get_note=get_note,
        get_children=get_children,
        max_note_characters=max_note_characters,
    )


def _root_path(
    *,
    note_id: str,
    get_note: Callable[[str], object],
) -> tuple[str, set[str]]:
    current_id = note_id
    path_ids: set[str] = set()
    while True:
        if current_id in path_ids:
            raise RuntimeError(f"Hierarchy cycle detected at {current_id}")
        path_ids.add(current_id)
        current = get_note(current_id)
        if current.parent_id is None:
            return current_id, path_ids
        current_id = current.parent_id


def _structure_nodes_by_root_id(
    *,
    structure_ids: set[str],
    root_id_by_structure_id: dict[str, str],
    get_note: Callable[[str], object],
    get_children: Callable[[Optional[str]], list[str]],
) -> DefaultDict[str, list[EvidenceTreeTokenSource]]:
    nodes_by_root_id: DefaultDict[
        str, list[EvidenceTreeTokenSource]
    ] = defaultdict(list)
    for note_id in structure_ids:
        record = get_note(note_id)
        parent_id = ""
        if record.parent_id is not None:
            parent_id = record.parent_id
        nodes_by_root_id[root_id_by_structure_id[note_id]].append(
            EvidenceTreeTokenSource(
                note_id=note_id,
                parent_id=parent_id,
                child_ids=tuple(
                    child_id
                    for child_id in get_children(note_id)
                    if child_id in structure_ids
                ),
            )
        )
    return nodes_by_root_id


def _timestamp_text(record: object, attribute_name: str) -> str:
    value = getattr(record, attribute_name)
    if value is None:
        return ""
    if not isinstance(value, datetime):
        raise TypeError(f"{attribute_name} must be datetime or None")
    return value.isoformat()
