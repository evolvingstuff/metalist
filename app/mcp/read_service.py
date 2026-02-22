from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import re
import unicodedata
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

_LIST_CHILDREN_WINDOW = 25
_ALLOWED_TAG_COUNT_MODES = frozenset({"effective", "raw"})
_ALLOWED_REGEX_TARGETS = frozenset({"content_text", "context_text", "both"})
_ALLOWED_REGEX_ENGINES = frozenset({"python-re", "re2"})
_ALLOWED_REGEX_FLAGS = frozenset({"i", "m", "s"})
_REGEX_MAX_PATTERN_LENGTH = 1000
_GET_NOTES_BATCH_MAX = 500
_REGEX_NORMALIZE_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u00A0": " ",
        "\u2007": " ",
        "\u202F": " ",
    }
)

try:
    import re2 as _re2_module
except ModuleNotFoundError:
    _re2_module = None


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
    def _ancestor_note_ids(self, *, note_id: str) -> List[str]:
        ancestors_reversed: List[str] = []
        visited: Set[str] = {note_id}
        current_id = note_id
        while True:
            record = note_store.get_note(current_id)
            parent_id = record.parent_id
            if parent_id is None:
                break
            if parent_id in visited:
                raise RuntimeError(f"Integrity failure: cycle detected while building ancestors for {note_id}")
            if not note_store.has_note(parent_id):
                raise RuntimeError(f"Integrity failure: missing parent note {parent_id} for {current_id}")
            visited.add(parent_id)
            ancestors_reversed.append(parent_id)
            current_id = parent_id
        return list(reversed(ancestors_reversed))

    def _descendant_note_ids_depth_first(self, *, note_id: str) -> List[str]:
        if not isinstance(note_id, str) or note_id == "":
            raise TypeError("note_id must be a non-empty string")
        ordered: List[str] = []

        def visit(parent_id: str) -> None:
            child_ids = note_store.get_children(parent_id)
            for child_id in child_ids:
                ordered.append(child_id)
                visit(child_id)

        visit(note_id)
        return ordered

    def _build_context_text(self, *, segments: List[str]) -> str:
        non_empty_segments = [segment.strip() for segment in segments if isinstance(segment, str) and segment.strip() != ""]
        return "\n\n---\n\n".join(non_empty_segments)

    def _normalize_regex_search_text(self, *, text: str) -> str:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        normalized = unicodedata.normalize("NFKC", text)
        normalized = normalized.translate(_REGEX_NORMALIZE_TRANSLATION)
        normalized = normalized.replace("\u2060", "")
        return normalized

    def _search_with_normalization_fallback(self, *, compiled, text: str):
        match = compiled.search(text)
        if match is not None:
            return match, text, False
        normalized_text = self._normalize_regex_search_text(text=text)
        if normalized_text == text:
            return None, text, False
        normalized_match = compiled.search(normalized_text)
        if normalized_match is None:
            return None, text, False
        return normalized_match, normalized_text, True

    def _build_ancestor_context_entries(self, *, note_id: str) -> List[Dict[str, object]]:
        entries: List[Dict[str, object]] = []
        for ancestor_id in self._ancestor_note_ids(note_id=note_id):
            ancestor_record = note_store.get_note(ancestor_id)
            entries.append(
                {
                    "note": {
                        "id": ancestor_record.id,
                        "parent_id": ancestor_record.parent_id,
                        "prev_id": ancestor_record.prev_id,
                        "next_id": ancestor_record.next_id,
                        "is_collapsed": bool(ancestor_record.is_collapsed),
                        "content": ancestor_record.content,
                        "content_text": strip_html(ancestor_record.content).strip(),
                        "created_at": _serialize_datetime(ancestor_record.created_at),
                        "updated_at": _serialize_datetime(ancestor_record.updated_at),
                    },
                    "tags": self._build_tags_payload(note_id=ancestor_id, record=ancestor_record),
                }
            )
        return entries

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
                    "content_text": strip_html(record.content).strip(),
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
        payload = self._build_note_node(note_id=normalized_note_id, visited=set())
        ancestors = self._build_ancestor_context_entries(note_id=normalized_note_id)
        current_note = payload["note"]
        if not isinstance(current_note, dict):
            raise RuntimeError("note payload missing note object")
        if "content_text" not in current_note:
            raise RuntimeError("note payload missing content_text")
        current_content_text = current_note["content_text"]
        if not isinstance(current_content_text, str):
            raise RuntimeError("content_text must be a string")

        ancestor_texts: List[str] = []
        for ancestor_entry in ancestors:
            if "note" not in ancestor_entry:
                raise RuntimeError("ancestor entry missing note payload")
            ancestor_note = ancestor_entry["note"]
            if not isinstance(ancestor_note, dict):
                raise RuntimeError("ancestor note payload must be an object")
            if "content_text" not in ancestor_note:
                raise RuntimeError("ancestor note payload missing content_text")
            ancestor_content_text = ancestor_note["content_text"]
            if not isinstance(ancestor_content_text, str):
                raise RuntimeError("ancestor content_text must be a string")
            ancestor_texts.append(ancestor_content_text)

        payload["ancestors"] = ancestors
        payload["context_text"] = self._build_context_text(segments=[*ancestor_texts, current_content_text])
        return payload

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
        child_ids_window = child_ids[:_LIST_CHILDREN_WINDOW]
        children_payload: List[Dict[str, object]] = []
        for child_id in child_ids_window:
            record = note_store.get_note(child_id)
            children_payload.append(
                {
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
                    "tags": self._build_tags_payload(note_id=child_id, record=record),
                    "child_count": len(note_store.get_children(child_id)),
                }
            )

        return {
            "parent_id": normalized_parent_id,
            "total_children": len(child_ids),
            "returned_count": len(children_payload),
            "has_more": len(child_ids) > len(children_payload),
            "children": children_payload,
        }

    def _raw_tag_frequencies(self) -> Dict[str, int]:
        counts = defaultdict(int)
        for note_id in note_store.list_note_ids():
            record = note_store.get_note(note_id)
            for term in record.non_meta_tag_terms:
                if term == "" or term.startswith("@"):
                    continue
                counts[term] += 1
        return dict(counts)

    def list_tags(self, *, prefix: object, limit: object, mode: object) -> Dict[str, object]:
        self._require_ready()

        if not isinstance(prefix, str):
            raise InvalidArgumentsError("prefix must be a string")
        if not isinstance(limit, int) or limit <= 0:
            raise InvalidArgumentsError("limit must be a positive integer")
        if not isinstance(mode, str):
            raise InvalidArgumentsError("mode must be a string")
        normalized_mode = mode.casefold()
        if normalized_mode not in _ALLOWED_TAG_COUNT_MODES:
            raise InvalidArgumentsError("mode must be one of: effective, raw")

        frequencies: Dict[str, int]
        if normalized_mode == "effective":
            frequencies = search_index.list_tag_frequencies()
        elif normalized_mode == "raw":
            frequencies = self._raw_tag_frequencies()
        else:
            raise RuntimeError(f"Unhandled tag count mode: {normalized_mode}")
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
            "mode": normalized_mode,
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

    def _normalize_note_id_list(self, *, note_ids: object, field_name: str) -> List[str]:
        if not isinstance(note_ids, list):
            raise InvalidArgumentsError(f"{field_name} must be a list of note ids")

        normalized: List[str] = []
        seen: Set[str] = set()
        for note_id in note_ids:
            if not isinstance(note_id, str) or note_id == "":
                raise InvalidArgumentsError(f"{field_name} entries must be non-empty strings")
            if note_id in seen:
                continue
            seen.add(note_id)
            normalized.append(note_id)
        return normalized

    def _require_bool(self, *, value: object, field_name: str) -> bool:
        if not isinstance(value, bool):
            raise InvalidArgumentsError(f"{field_name} must be a boolean")
        return value

    def _normalize_regex_flags(self, *, flags: object) -> tuple[str, int]:
        if not isinstance(flags, str):
            raise InvalidArgumentsError("flags must be a string")

        normalized = ""
        seen = set()
        for char in flags:
            if char in seen:
                continue
            if char not in _ALLOWED_REGEX_FLAGS:
                raise InvalidArgumentsError(f"Unsupported regex flag: {char}")
            seen.add(char)
            normalized += char

        ordered_flags = "".join(char for char in "ims" if char in normalized)
        python_flags = 0
        if "i" in ordered_flags:
            python_flags |= re.IGNORECASE
        if "m" in ordered_flags:
            python_flags |= re.MULTILINE
        if "s" in ordered_flags:
            python_flags |= re.DOTALL
        return ordered_flags, python_flags

    def _compile_regex(self, *, pattern: object, flags: object, engine: object):
        if not isinstance(pattern, str) or pattern == "":
            raise InvalidArgumentsError("pattern must be a non-empty string")
        if len(pattern) > _REGEX_MAX_PATTERN_LENGTH:
            raise InvalidArgumentsError(
                f"pattern exceeds max length {_REGEX_MAX_PATTERN_LENGTH}"
            )
        if not isinstance(engine, str):
            raise InvalidArgumentsError("regex_engine must be a string")
        normalized_engine = engine.casefold()
        if normalized_engine not in _ALLOWED_REGEX_ENGINES:
            raise InvalidArgumentsError("regex_engine must be one of: python-re, re2")

        normalized_flags, python_flags = self._normalize_regex_flags(flags=flags)

        if normalized_engine == "python-re":
            try:
                compiled = re.compile(pattern, python_flags)
            except re.error as error:
                raise InvalidArgumentsError(f"invalid regex pattern: {error}") from error
            return compiled, normalized_flags, normalized_engine

        if _re2_module is None:
            raise InvalidArgumentsError("regex_engine re2 requested but re2 module is not installed")

        re2_flags = 0
        if "i" in normalized_flags and hasattr(_re2_module, "IGNORECASE"):
            re2_flags |= _re2_module.IGNORECASE
        if "m" in normalized_flags and hasattr(_re2_module, "MULTILINE"):
            re2_flags |= _re2_module.MULTILINE
        if "s" in normalized_flags and hasattr(_re2_module, "DOTALL"):
            re2_flags |= _re2_module.DOTALL

        try:
            compiled = _re2_module.compile(pattern, re2_flags)
        except Exception as error:
            raise InvalidArgumentsError(f"invalid re2 pattern: {error}") from error
        return compiled, normalized_flags, normalized_engine

    def _match_snippet(
        self,
        *,
        text: str,
        start: int,
        end: int,
        window: int = 80,
    ) -> str:
        left = max(0, start - window)
        right = min(len(text), end + window)
        snippet = text[left:right]
        if left > 0:
            snippet = "..." + snippet
        if right < len(text):
            snippet = snippet + "..."
        return snippet

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

    def _build_note_context_bundle(
        self,
        *,
        note_id: str,
        content_text: str,
    ) -> Dict[str, object]:
        ancestor_note_ids = self._ancestor_note_ids(note_id=note_id)
        ancestor_texts: List[str] = []
        for ancestor_note_id in ancestor_note_ids:
            ancestor_record = note_store.get_note(ancestor_note_id)
            ancestor_texts.append(strip_html(ancestor_record.content).strip())

        descendant_note_ids = self._descendant_note_ids_depth_first(note_id=note_id)
        descendant_texts: List[str] = []
        for descendant_note_id in descendant_note_ids:
            descendant_record = note_store.get_note(descendant_note_id)
            descendant_texts.append(strip_html(descendant_record.content).strip())

        context_text = self._build_context_text(
            segments=[*ancestor_texts, content_text, *descendant_texts]
        )
        return {
            "ancestor_note_ids": ancestor_note_ids,
            "ancestor_texts": ancestor_texts,
            "descendant_note_ids": descendant_note_ids,
            "descendant_texts": descendant_texts,
            "context_text": context_text,
        }

    def _search_result_entry(self, *, note_id: str, note_order_index: int) -> Dict[str, object]:
        record = note_store.get_note(note_id)
        content_text = strip_html(record.content).strip()
        preview_text = content_text
        if len(preview_text) > 140:
            truncated = preview_text[:140]
        else:
            truncated = preview_text

        context_bundle = self._build_note_context_bundle(
            note_id=note_id,
            content_text=content_text,
        )
        ancestor_note_ids = context_bundle["ancestor_note_ids"]
        if not isinstance(ancestor_note_ids, list):
            raise RuntimeError("ancestor_note_ids must be a list")
        ancestor_texts = context_bundle["ancestor_texts"]
        if not isinstance(ancestor_texts, list):
            raise RuntimeError("ancestor_texts must be a list")
        descendant_note_ids = context_bundle["descendant_note_ids"]
        if not isinstance(descendant_note_ids, list):
            raise RuntimeError("descendant_note_ids must be a list")
        descendant_texts = context_bundle["descendant_texts"]
        if not isinstance(descendant_texts, list):
            raise RuntimeError("descendant_texts must be a list")
        context_text = context_bundle["context_text"]
        if not isinstance(context_text, str):
            raise RuntimeError("context_text must be a string")

        tags_payload = self._build_tags_payload(note_id=note_id, record=record)
        if "raw_tag_string" not in tags_payload:
            raise RuntimeError("tags payload missing raw_tag_string")
        if "tag_terms" not in tags_payload:
            raise RuntimeError("tags payload missing tag_terms")
        if "implied_tag_terms" not in tags_payload:
            raise RuntimeError("tags payload missing implied_tag_terms")
        if "effective_tag_terms" not in tags_payload:
            raise RuntimeError("tags payload missing effective_tag_terms")

        return {
            "note_id": record.id,
            "parent_id": record.parent_id,
            "updated_at": _serialize_datetime(record.updated_at),
            "note_order_index": note_order_index,
            "raw_tag_string": tags_payload["raw_tag_string"],
            "tag_terms": tags_payload["tag_terms"],
            "implied_tag_terms": tags_payload["implied_tag_terms"],
            "effective_tag_terms": tags_payload["effective_tag_terms"],
            "preview_text": truncated,
            "content_text": content_text,
            "ancestor_note_ids": ancestor_note_ids,
            "ancestor_texts": ancestor_texts,
            "descendant_note_ids": descendant_note_ids,
            "descendant_texts": descendant_texts,
            "context_text": context_text,
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
        order_index_by_id = {note_id: index for index, note_id in enumerate(ordered_ids)}
        if combined_query == "":
            matched_ids = set(ordered_ids)
        else:
            matched_ids = search_index.query_note_ids(combined_query)

        ordered_matches = [note_id for note_id in ordered_ids if note_id in matched_ids]
        total_matches = len(ordered_matches)

        sliced_matches = ordered_matches[offset : offset + limit]
        results = [
            self._search_result_entry(
                note_id=note_id,
                note_order_index=order_index_by_id.get(note_id, 10**9),
            )
            for note_id in sliced_matches
        ]

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

    def search_note_ids(
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
            ordered_matches = ordered_ids
        else:
            matched_ids = search_index.query_note_ids(combined_query)
            ordered_matches = [note_id for note_id in ordered_ids if note_id in matched_ids]

        total_matches = len(ordered_matches)
        sliced_note_ids = ordered_matches[offset : offset + limit]

        return {
            "query": query,
            "required_tags": normalized_required,
            "forbidden_tags": normalized_forbidden,
            "resolved_query": combined_query,
            "limit": limit,
            "offset": offset,
            "total_matches": total_matches,
            "returned_count": len(sliced_note_ids),
            "note_ids": sliced_note_ids,
        }

    def search_notes_regex(
        self,
        *,
        pattern: object,
        flags: object,
        regex_engine: object,
        target: object,
        scope_note_ids: object,
        limit: object,
        offset: object,
    ) -> Dict[str, object]:
        self._require_ready()

        if not isinstance(target, str):
            raise InvalidArgumentsError("target must be a string")
        normalized_target = target.casefold()
        if normalized_target not in _ALLOWED_REGEX_TARGETS:
            raise InvalidArgumentsError("target must be one of: content_text, context_text, both")
        if not isinstance(limit, int) or limit <= 0:
            raise InvalidArgumentsError("limit must be a positive integer")
        if not isinstance(offset, int) or offset < 0:
            raise InvalidArgumentsError("offset must be a non-negative integer")

        ordered_scope_note_ids = self._normalize_note_id_list(
            note_ids=scope_note_ids,
            field_name="scope_note_ids",
        )
        effective_scope_note_ids = ordered_scope_note_ids
        if len(effective_scope_note_ids) == 0:
            effective_scope_note_ids = self._depth_first_note_order()
        for note_id in effective_scope_note_ids:
            if not note_store.has_note(note_id):
                raise InvalidArgumentsError(f"scope_note_ids includes unknown note id: {note_id}")

        compiled, normalized_flags, normalized_engine = self._compile_regex(
            pattern=pattern,
            flags=flags,
            engine=regex_engine,
        )
        if not isinstance(pattern, str):
            raise TypeError("pattern should be string after compile validation")

        matched_results: List[Dict[str, object]] = []
        for scope_index, note_id in enumerate(effective_scope_note_ids):
            record = note_store.get_note(note_id)
            content_text = strip_html(record.content).strip()

            context_text = ""
            if normalized_target in {"context_text", "both"}:
                context_bundle = self._build_note_context_bundle(
                    note_id=note_id,
                    content_text=content_text,
                )
                context_value = context_bundle.get("context_text")
                if not isinstance(context_value, str):
                    raise RuntimeError("context_text must be a string")
                context_text = context_value

            field_matches: List[Dict[str, object]] = []
            if normalized_target in {"content_text", "both"}:
                match, matched_text, normalized_used = self._search_with_normalization_fallback(
                    compiled=compiled,
                    text=content_text,
                )
                if match is not None:
                    field_matches.append(
                        {
                            "field": "content_text",
                            "start": int(match.start()),
                            "end": int(match.end()),
                            "snippet": self._match_snippet(
                                text=matched_text,
                                start=int(match.start()),
                                end=int(match.end()),
                            ),
                            "normalized_text_match": normalized_used,
                        }
                    )

            if normalized_target in {"context_text", "both"}:
                match, matched_text, normalized_used = self._search_with_normalization_fallback(
                    compiled=compiled,
                    text=context_text,
                )
                if match is not None:
                    field_matches.append(
                        {
                            "field": "context_text",
                            "start": int(match.start()),
                            "end": int(match.end()),
                            "snippet": self._match_snippet(
                                text=matched_text,
                                start=int(match.start()),
                                end=int(match.end()),
                            ),
                            "normalized_text_match": normalized_used,
                        }
                    )

            if len(field_matches) == 0:
                continue

            search_entry = self._search_result_entry(
                note_id=note_id,
                note_order_index=scope_index,
            )
            matched_results.append(
                {
                    **search_entry,
                    "matches": field_matches,
                }
            )

        total_matches = len(matched_results)
        sliced_matches = matched_results[offset : offset + limit]
        return {
            "pattern": pattern,
            "flags": normalized_flags,
            "regex_engine": normalized_engine,
            "target": normalized_target,
            "scope_count": len(effective_scope_note_ids),
            "limit": limit,
            "offset": offset,
            "total_matches": total_matches,
            "returned_count": len(sliced_matches),
            "results": sliced_matches,
        }

    def search_notes_regex_ids(
        self,
        *,
        pattern: object,
        flags: object,
        regex_engine: object,
        target: object,
        scope_note_ids: object,
        limit: object,
        offset: object,
    ) -> Dict[str, object]:
        self._require_ready()

        if not isinstance(target, str):
            raise InvalidArgumentsError("target must be a string")
        normalized_target = target.casefold()
        if normalized_target not in _ALLOWED_REGEX_TARGETS:
            raise InvalidArgumentsError("target must be one of: content_text, context_text, both")
        if not isinstance(limit, int) or limit <= 0:
            raise InvalidArgumentsError("limit must be a positive integer")
        if not isinstance(offset, int) or offset < 0:
            raise InvalidArgumentsError("offset must be a non-negative integer")

        ordered_scope_note_ids = self._normalize_note_id_list(
            note_ids=scope_note_ids,
            field_name="scope_note_ids",
        )
        effective_scope_note_ids = ordered_scope_note_ids
        if len(effective_scope_note_ids) == 0:
            effective_scope_note_ids = self._depth_first_note_order()
        for note_id in effective_scope_note_ids:
            if not note_store.has_note(note_id):
                raise InvalidArgumentsError(f"scope_note_ids includes unknown note id: {note_id}")

        compiled, normalized_flags, normalized_engine = self._compile_regex(
            pattern=pattern,
            flags=flags,
            engine=regex_engine,
        )
        if not isinstance(pattern, str):
            raise TypeError("pattern should be string after compile validation")

        matched_note_ids: List[str] = []
        for note_id in effective_scope_note_ids:
            record = note_store.get_note(note_id)
            content_text = strip_html(record.content).strip()

            context_text = ""
            if normalized_target in {"context_text", "both"}:
                context_bundle = self._build_note_context_bundle(
                    note_id=note_id,
                    content_text=content_text,
                )
                context_value = context_bundle.get("context_text")
                if not isinstance(context_value, str):
                    raise RuntimeError("context_text must be a string")
                context_text = context_value

            matched = False
            if normalized_target in {"content_text", "both"}:
                match, _, _ = self._search_with_normalization_fallback(
                    compiled=compiled,
                    text=content_text,
                )
                if match is not None:
                    matched = True
            if not matched and normalized_target in {"context_text", "both"}:
                match, _, _ = self._search_with_normalization_fallback(
                    compiled=compiled,
                    text=context_text,
                )
                if match is not None:
                    matched = True
            if not matched:
                continue

            matched_note_ids.append(record.id)

        total_matches = len(matched_note_ids)
        sliced_note_ids = matched_note_ids[offset : offset + limit]
        return {
            "pattern": pattern,
            "flags": normalized_flags,
            "regex_engine": normalized_engine,
            "target": normalized_target,
            "scope_count": len(effective_scope_note_ids),
            "limit": limit,
            "offset": offset,
            "total_matches": total_matches,
            "returned_count": len(sliced_note_ids),
            "note_ids": sliced_note_ids,
        }

    def get_notes_batch(
        self,
        *,
        note_ids: object,
        include_content_text: object,
        include_context_text: object,
        include_tags: object,
        include_ancestors: object,
        include_descendants: object,
    ) -> Dict[str, object]:
        self._require_ready()

        normalized_note_ids = self._normalize_note_id_list(
            note_ids=note_ids,
            field_name="note_ids",
        )
        if len(normalized_note_ids) > _GET_NOTES_BATCH_MAX:
            raise InvalidArgumentsError(f"note_ids exceeds max batch size {_GET_NOTES_BATCH_MAX}")

        should_include_content_text = self._require_bool(
            value=include_content_text,
            field_name="include_content_text",
        )
        should_include_context_text = self._require_bool(
            value=include_context_text,
            field_name="include_context_text",
        )
        should_include_tags = self._require_bool(
            value=include_tags,
            field_name="include_tags",
        )
        should_include_ancestors = self._require_bool(
            value=include_ancestors,
            field_name="include_ancestors",
        )
        should_include_descendants = self._require_bool(
            value=include_descendants,
            field_name="include_descendants",
        )

        notes_payload: List[Dict[str, object]] = []
        not_found_ids: List[str] = []
        for note_id in normalized_note_ids:
            if not note_store.has_note(note_id):
                not_found_ids.append(note_id)
                continue

            record = note_store.get_note(note_id)
            content_text = strip_html(record.content).strip()
            ancestor_note_ids = self._ancestor_note_ids(note_id=note_id)

            ancestor_texts: List[str] = []
            if should_include_context_text or should_include_ancestors:
                for ancestor_note_id in ancestor_note_ids:
                    ancestor_record = note_store.get_note(ancestor_note_id)
                    ancestor_texts.append(strip_html(ancestor_record.content).strip())

            descendant_note_ids: List[str] = []
            descendant_texts: List[str] = []
            if should_include_context_text or should_include_descendants:
                descendant_note_ids = self._descendant_note_ids_depth_first(note_id=note_id)
                for descendant_note_id in descendant_note_ids:
                    descendant_record = note_store.get_note(descendant_note_id)
                    descendant_texts.append(strip_html(descendant_record.content).strip())

            entry: Dict[str, object] = {
                "note_id": record.id,
                "parent_id": record.parent_id,
                "updated_at": _serialize_datetime(record.updated_at),
            }
            if should_include_content_text:
                entry["content_text"] = content_text
            if should_include_context_text:
                entry["context_text"] = self._build_context_text(
                    segments=[*ancestor_texts, content_text, *descendant_texts]
                )
            if should_include_tags:
                entry["tags"] = self._build_tags_payload(note_id=note_id, record=record)
            if should_include_ancestors:
                entry["ancestor_note_ids"] = ancestor_note_ids
                entry["ancestor_texts"] = ancestor_texts
            if should_include_descendants:
                entry["descendant_note_ids"] = descendant_note_ids
                entry["descendant_texts"] = descendant_texts
            notes_payload.append(entry)

        return {
            "total_requested": len(normalized_note_ids),
            "returned_count": len(notes_payload),
            "not_found_ids": not_found_ids,
            "notes": notes_payload,
        }
