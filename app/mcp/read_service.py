from __future__ import annotations

from datetime import datetime
from typing import Dict, FrozenSet, List, Set

from app.config import VERSION
from app.services.note_store import NoteRecord
from app.services.note_store import store as note_store
from app.services.ontology_rules_store import get_ontology
from app.services.search_index import search_index
from app.utils.text_utils import strip_html

from .errors import InvalidArgumentsError
from .errors import NoteNotFoundError
from .errors import VaultNotReadyError


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"datetime value must be datetime|None, got {type(value)}")
    return value.isoformat()


def _normalize_terms(terms: FrozenSet[str]) -> List[str]:
    normalized = [term for term in terms if term]
    normalized.sort()
    return normalized


class ReadService:
    def _require_ready(self) -> None:
        if not note_store.loaded:
            raise VaultNotReadyError("Vault locked or not hydrated")

    def _require_note_id(self, note_id: object) -> str:
        if not isinstance(note_id, str) or note_id == "":
            raise InvalidArgumentsError("note_id must be a non-empty string")
        return note_id

    def _require_note_exists(self, note_id: str) -> None:
        if not note_store.has_note(note_id):
            raise NoteNotFoundError(f"Note not found: {note_id}")

    def _effective_base_terms(self, *, note_id: str, record: NoteRecord) -> FrozenSet[str]:
        inherited_non_meta = note_store.get_inherited_non_meta_tag_terms(note_id)
        merged = set(record.tag_terms)
        merged.update(inherited_non_meta)
        return frozenset(merged)

    def _build_tags_payload(self, *, note_id: str, record: NoteRecord) -> Dict[str, object]:
        base_terms = self._effective_base_terms(note_id=note_id, record=record)
        ontology = get_ontology()

        implication_closure = ontology.infer_implication_only(base_tags=base_terms)
        implied_only = frozenset(term for term in implication_closure if term not in base_terms)

        plaintext = strip_html(record.content)
        effective_terms = ontology.infer_effective_tags(
            base_tags=base_terms,
            plaintext=plaintext,
        )

        return {
            "raw_tag_string": record.tags,
            "tag_terms": _normalize_terms(record.tag_terms),
            "implied_tag_terms": _normalize_terms(implied_only),
            "effective_tag_terms": _normalize_terms(effective_terms),
        }

    def _build_note_node(self, *, note_id: str, visited: Set[str]) -> Dict[str, object]:
        if note_id in visited:
            raise RuntimeError(f"Integrity failure: cycle detected at note {note_id}")
        visited.add(note_id)
        try:
            record = note_store.get_note(note_id)
            children_ids = note_store.get_children(note_id)
            child_nodes = [
                self._build_note_node(note_id=child_id, visited=visited)
                for child_id in children_ids
            ]

            return {
                "note": {
                    "id": record.id,
                    "parent_id": record.parent_id,
                    "prev_id": record.prev_id,
                    "next_id": record.next_id,
                    "is_collapsed": bool(record.is_collapsed),
                    "content": record.content,
                    "created_at": _serialize_datetime(record.created_at),
                    "updated_at": _serialize_datetime(record.updated_at),
                },
                "tags": self._build_tags_payload(note_id=note_id, record=record),
                "children": child_nodes,
            }
        finally:
            visited.remove(note_id)

    def health_check(self) -> Dict[str, object]:
        return {
            "server": "metalist-mcp-readonly",
            "version": VERSION,
            "ready": bool(note_store.loaded),
        }

    def count_notes(self) -> Dict[str, object]:
        self._require_ready()
        ordered_ids = self._depth_first_note_order()
        return {
            "total_notes": len(ordered_ids),
        }

    def get_note(self, *, note_id: object) -> Dict[str, object]:
        self._require_ready()
        normalized_note_id = self._require_note_id(note_id)
        self._require_note_exists(normalized_note_id)
        return self._build_note_node(note_id=normalized_note_id, visited=set())

    def list_children(self, *, parent_id: object) -> Dict[str, object]:
        self._require_ready()

        normalized_parent_id: str | None
        if parent_id is None:
            normalized_parent_id = None
        else:
            if not isinstance(parent_id, str) or parent_id == "":
                raise InvalidArgumentsError("parent_id must be null or a non-empty string")
            self._require_note_exists(parent_id)
            normalized_parent_id = parent_id

        child_ids = note_store.get_children(normalized_parent_id)
        return {
            "parent_id": normalized_parent_id,
            "children": child_ids,
            "returned_count": len(child_ids),
        }

    def list_tags(self, *, prefix: object, limit: object) -> Dict[str, object]:
        self._require_ready()

        if not isinstance(prefix, str):
            raise InvalidArgumentsError("prefix must be a string")
        if not isinstance(limit, int) or limit <= 0:
            raise InvalidArgumentsError("limit must be a positive integer")

        frequencies = search_index.list_tag_frequencies()
        prefix_casefold = prefix.casefold()

        filtered = [
            (tag, count)
            for tag, count in frequencies.items()
            if tag and tag.casefold().startswith(prefix_casefold)
        ]
        filtered.sort(key=lambda item: (-item[1], item[0]))

        total_matches = len(filtered)
        sliced = filtered[:limit]
        tags = [{"tag": tag, "count": count} for tag, count in sliced]
        return {
            "prefix": prefix,
            "limit": limit,
            "total_matches": total_matches,
            "returned_count": len(tags),
            "tags": tags,
        }

    def _depth_first_note_order(self) -> List[str]:
        ordered: List[str] = []

        def visit(parent_id: str | None) -> None:
            child_ids = note_store.get_children(parent_id)
            for child_id in child_ids:
                ordered.append(child_id)
                visit(child_id)

        visit(None)
        return ordered

    def _normalize_tag_filters(self, *, values: object, field_name: str) -> List[str]:
        if not isinstance(values, list):
            raise InvalidArgumentsError(f"{field_name} must be a list of strings")

        seen: Set[str] = set()
        normalized: List[str] = []
        for value in values:
            if not isinstance(value, str) or value == "":
                raise InvalidArgumentsError(f"{field_name} entries must be non-empty strings")
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _build_search_query(
        self,
        *,
        query: str,
        required_tags: List[str],
        forbidden_tags: List[str],
    ) -> str:
        parts: List[str] = []
        if query != "":
            parts.append(query)
        parts.extend(required_tags)
        parts.extend(f"-{tag}" for tag in forbidden_tags)
        return " ".join(parts).strip()

    def _search_result_entry(self, *, note_id: str) -> Dict[str, object]:
        record = note_store.get_note(note_id)
        preview_text = strip_html(record.content).strip()
        if len(preview_text) > 140:
            truncated = preview_text[:140]
        else:
            truncated = preview_text

        return {
            "note_id": record.id,
            "parent_id": record.parent_id,
            "updated_at": _serialize_datetime(record.updated_at),
            "raw_tag_string": record.tags,
            "tag_terms": _normalize_terms(record.tag_terms),
            "preview_text": truncated,
        }

    def search_notes(
        self,
        *,
        query: object,
        required_tags: object,
        forbidden_tags: object,
        limit: object,
        offset: object,
    ) -> Dict[str, object]:
        self._require_ready()

        if not isinstance(query, str):
            raise InvalidArgumentsError("query must be a string")
        if not isinstance(limit, int) or limit <= 0:
            raise InvalidArgumentsError("limit must be a positive integer")
        if not isinstance(offset, int) or offset < 0:
            raise InvalidArgumentsError("offset must be a non-negative integer")

        normalized_required = self._normalize_tag_filters(
            values=required_tags,
            field_name="required_tags",
        )
        normalized_forbidden = self._normalize_tag_filters(
            values=forbidden_tags,
            field_name="forbidden_tags",
        )

        combined_query = self._build_search_query(
            query=query,
            required_tags=normalized_required,
            forbidden_tags=normalized_forbidden,
        )

        ordered_ids = self._depth_first_note_order()
        if combined_query == "":
            matched_ids = set(ordered_ids)
        else:
            matched_ids = search_index.query_note_ids(combined_query)

        ordered_matches = [note_id for note_id in ordered_ids if note_id in matched_ids]
        total_matches = len(ordered_matches)

        sliced_matches = ordered_matches[offset : offset + limit]
        results = [self._search_result_entry(note_id=note_id) for note_id in sliced_matches]

        return {
            "query": query,
            "required_tags": normalized_required,
            "forbidden_tags": normalized_forbidden,
            "resolved_query": combined_query,
            "limit": limit,
            "offset": offset,
            "total_matches": total_matches,
            "returned_count": len(results),
            "results": results,
        }
