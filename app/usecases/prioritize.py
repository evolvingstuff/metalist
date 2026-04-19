from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict
from typing import Dict, List, Optional

from app.services.search_index import extract_tags_for_search
from app.services.search_index import search_index
from app.services.snapshot import resolve_search_scope
from app.services.store import store
from app.services.tag_term_matching import tag_term_matches_prefix
from app.services.sync import generate_new_uuid
from app.services.tag_ontology import is_valid_tag_token
from app.services.undo_state import record_move_batch
from app.usecases.base import QueryCommand
from app.usecases.move import _assert_neighbors, _neighbors, apply_move


def _normalize_direction(direction: str) -> str:
    if not isinstance(direction, str):
        raise TypeError(f"direction must be a string, got {type(direction)}")
    normalized = direction.strip().lower()
    if normalized not in {"front", "back"}:
        raise ValueError("direction must be 'front' or 'back'")
    return normalized


def _normalize_tag(tag: str) -> str:
    if not isinstance(tag, str):
        raise TypeError(f"tag must be a string, got {type(tag)}")
    normalized = tag.strip()
    if normalized == "":
        raise ValueError("tag must be a non-empty tag token")
    if not is_valid_tag_token(normalized):
        raise ValueError("tag must be a single valid tag token")
    return normalized


def _resolve_visible_root_ids(search_query: Optional[str]) -> List[str]:
    if search_query is not None and not isinstance(search_query, str):
        raise TypeError(f"search_query must be a string or None, got {type(search_query)}")

    normalized_search = search_query
    if isinstance(normalized_search, str) and normalized_search.strip() == "":
        normalized_search = None

    if normalized_search is None:
        return store.children(None)

    search_scope = resolve_search_scope(
        search=normalized_search,
        editing_note_id=None,
        sort_mode="normal",
        ordered_root_ids=None,
    )
    if not search_scope.search_active or search_scope.search_root_ids_ordered is None:
        return store.children(None)
    return list(search_scope.search_root_ids_ordered)


def _build_target_root_ids(
    *,
    ordered_root_ids: List[str],
    visible_root_ids: List[str],
    matching_root_ids: List[str],
    direction: str,
) -> List[str]:
    visible_root_id_set = set(visible_root_ids)
    if len(visible_root_id_set) != len(visible_root_ids):
        raise RuntimeError("Visible root ids must be unique")

    matching_root_id_set = set(matching_root_ids)
    non_matching_root_ids = [
        root_id for root_id in visible_root_ids if root_id not in matching_root_id_set
    ]
    if direction == "front":
        desired_visible_root_ids = matching_root_ids + non_matching_root_ids
    else:
        desired_visible_root_ids = non_matching_root_ids + matching_root_ids

    desired_index = 0
    target_root_ids: List[str] = []
    for root_id in ordered_root_ids:
        if root_id in visible_root_id_set:
            if desired_index >= len(desired_visible_root_ids):
                raise RuntimeError("Desired visible root ids exhausted during root order reconstruction")
            target_root_ids.append(desired_visible_root_ids[desired_index])
            desired_index += 1
        else:
            target_root_ids.append(root_id)

    if desired_index != len(desired_visible_root_ids):
        raise RuntimeError("Desired visible root ids overflowed root order reconstruction")
    return target_root_ids


def list_prioritize_tag_suggestions(
    *,
    search_query: Optional[str],
    query: str,
    limit: int,
) -> List[str]:
    if not isinstance(query, str):
        raise TypeError(f"query must be a string, got {type(query)}")
    if not isinstance(limit, int) or limit <= 0:
        raise TypeError("limit must be a positive integer")

    normalized_prefix = query.strip()
    visible_root_ids = _resolve_visible_root_ids(search_query)

    total_counts: DefaultDict[str, int] = defaultdict(int)
    representative_counts: DefaultDict[str, Dict[str, int]] = defaultdict(dict)
    direct_prefix_matches: Dict[str, bool] = {}
    first_seen_indices: Dict[str, int] = {}
    next_index = 0

    for root_id in visible_root_ids:
        record = store.get(root_id)
        if not isinstance(record.tags, str):
            raise RuntimeError(f"Note tags must be a string | note_id={root_id}")
        for tag in extract_tags_for_search(record.tags):
            if normalized_prefix != "" and not tag_term_matches_prefix(term=tag, prefix=normalized_prefix):
                continue
            tag_casefold = tag.casefold()
            total_counts[tag_casefold] += 1
            spelling_counts = representative_counts[tag_casefold]
            if tag not in spelling_counts:
                spelling_counts[tag] = 0
            spelling_counts[tag] += 1
            if tag not in first_seen_indices:
                first_seen_indices[tag] = next_index
                next_index += 1
            if tag_casefold not in direct_prefix_matches:
                direct_prefix_matches[tag_casefold] = tag.casefold().startswith(normalized_prefix.casefold())
            elif not direct_prefix_matches[tag_casefold] and tag.casefold().startswith(normalized_prefix.casefold()):
                direct_prefix_matches[tag_casefold] = True

    scored_terms: List[tuple[int, int, str, str]] = []
    for tag_casefold, count in total_counts.items():
        spellings = representative_counts[tag_casefold]
        representative = sorted(
            spellings.items(),
            key=lambda item: (-item[1], first_seen_indices[item[0]], item[0].casefold(), item[0]),
        )[0][0]
        direct_prefix_score = 0
        if tag_casefold in direct_prefix_matches and direct_prefix_matches[tag_casefold]:
            direct_prefix_score = 1
        scored_terms.append(
            (
                direct_prefix_score,
                count,
                representative.casefold(),
                representative,
            )
        )

    scored_terms.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    return [representative for _, _, _, representative in scored_terms[:limit]]


@dataclass
class CmdPrioritize(QueryCommand):
    tag: str
    direction: str
    search_query: Optional[str]
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return (
            f"CmdPrioritize(tag={self.tag!r}, direction={self.direction!r}, "
            f"client={self.client_id})"
        )

    def execute(self) -> Dict[str, object]:
        normalized_tag = _normalize_tag(self.tag)
        normalized_direction = _normalize_direction(self.direction)

        ordered_root_ids = store.children(None)
        visible_root_ids = _resolve_visible_root_ids(self.search_query)
        matching_note_ids = set(search_index.query_note_ids(normalized_tag))
        matching_root_ids = [
            root_id for root_id in visible_root_ids if root_id in matching_note_ids
        ]

        if len(matching_root_ids) == 0:
            return {
                "status": "noop",
                "reason": "no_matches",
                "matchedRootCount": 0,
                "visibleRootCount": len(visible_root_ids),
            }

        target_root_ids = _build_target_root_ids(
            ordered_root_ids=ordered_root_ids,
            visible_root_ids=visible_root_ids,
            matching_root_ids=matching_root_ids,
            direction=normalized_direction,
        )
        if target_root_ids == ordered_root_ids:
            return {
                "status": "noop",
                "reason": "already_prioritized",
                "matchedRootCount": len(matching_root_ids),
                "visibleRootCount": len(visible_root_ids),
            }

        simulated_root_ids = list(ordered_root_ids)
        move_ops: List[Dict[str, object]] = []

        for target_index, note_id in enumerate(target_root_ids):
            current_index = simulated_root_ids.index(note_id)
            if current_index == target_index:
                continue

            before_parent, before_prev, before_next = _neighbors(note_id)
            if before_parent is not None:
                raise RuntimeError(
                    "Prioritize only supports root notes in v1: "
                    f"note_id={note_id} parent_id={before_parent}"
                )

            record = store.get(note_id)
            if not isinstance(record.tags, str):
                raise RuntimeError(f"Note tags must be a string | note_id={note_id}")
            tags = record.tags

            simulated_without = simulated_root_ids[:current_index] + simulated_root_ids[current_index + 1:]
            if target_index == 0:
                dest_prev = None
            else:
                dest_prev = simulated_without[target_index - 1]
            if target_index >= len(simulated_without):
                dest_next = None
            else:
                dest_next = simulated_without[target_index]

            apply_move(note_id, None, dest_prev, dest_next)
            _assert_neighbors(note_id, None, dest_prev, dest_next)

            move_ops.append(
                {
                    "note_id": note_id,
                    "before_parent": before_parent,
                    "before_prev": before_prev,
                    "before_next": before_next,
                    "before_tags": tags,
                    "after_parent": None,
                    "after_prev": dest_prev,
                    "after_next": dest_next,
                    "after_tags": tags,
                }
            )

            simulated_root_ids = list(simulated_without)
            simulated_root_ids.insert(target_index, note_id)

        if simulated_root_ids != target_root_ids:
            raise RuntimeError(
                "Prioritize failed to realize target order: "
                f"actual={simulated_root_ids} target={target_root_ids}"
            )

        if len(move_ops) == 0:
            return {
                "status": "noop",
                "reason": "already_prioritized",
                "matchedRootCount": len(matching_root_ids),
                "visibleRootCount": len(visible_root_ids),
            }

        record_move_batch(
            self.client_id,
            self.undo_context,
            move_ops=move_ops,
            viewport=self.viewport,
        )

        return {
            "status": "moved",
            "movedRootCount": len(move_ops),
            "matchedRootCount": len(matching_root_ids),
            "visibleRootCount": len(visible_root_ids),
            "updateUUID": generate_new_uuid(),
        }
