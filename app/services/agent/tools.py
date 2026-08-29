"""Read-only PKMS-domain tools exposed to the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.services.agent.actions import ReadNotesByIdAction
from app.services.agent.actions import SearchNotesAction
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.content_formatting import extract_note_text_for_agent
from app.services.note_store import NoteRecord
from app.services.note_store import NoteStore
from app.services.note_store import store as note_store
from app.services.search_index import SearchIndex
from app.services.search_index import search_index


class ToolPermission(str, Enum):
    READ = "read"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    mutates: bool
    permission: ToolPermission


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    action_name: str
    status_label: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class _PreparedNoteDisclosure:
    record: NoteRecord
    root_note_id: str
    content_text: str
    content_is_redacted: bool


class ReadOnlyAgentToolRegistry:
    def __init__(self, *, notes: NoteStore, searches: SearchIndex) -> None:
        self._notes = notes
        self._searches = searches

    def spec_for(self, action: object) -> ToolSpec:
        if isinstance(action, SearchNotesAction):
            return ToolSpec(
                name="search_notes",
                description=(
                    "Search the in-memory MetaList note index and return a bounded "
                    "page containing only matching note nodes"
                ),
                mutates=False,
                permission=ToolPermission.READ,
            )
        if isinstance(action, ReadNotesByIdAction):
            return ToolSpec(
                name="read_notes_by_id",
                description=(
                    "Read bounded content from notes with already-known UUIDs in the "
                    "in-memory MetaList store"
                ),
                mutates=False,
                permission=ToolPermission.READ,
            )
        raise TypeError(f"No tool corresponds to action type {type(action).__name__}")

    def execute(
        self,
        action: object,
        *,
        settings: AgentRetrievalSettings,
    ) -> ToolExecutionResult:
        if not isinstance(settings, AgentRetrievalSettings):
            raise TypeError("Agent tool execution requires retrieval settings")
        if isinstance(action, SearchNotesAction):
            return self._search_notes(action, settings=settings)
        if isinstance(action, ReadNotesByIdAction):
            return self._read_notes_by_id(action, settings=settings)
        raise TypeError(f"Cannot execute action type {type(action).__name__}")

    def _search_notes(
        self,
        action: SearchNotesAction,
        *,
        settings: AgentRetrievalSettings,
    ) -> ToolExecutionResult:
        matched_ids = self._searches.query_note_ids(action.query)
        all_note_ids = self._notes.list_note_ids()
        assert matched_ids.issubset(set(all_note_ids))
        ordered_ids = self._ordered_matching_note_ids(
            matched_ids=matched_ids,
            all_note_ids=all_note_ids,
        )
        ordered_root_ids: list[str] = []
        seen_root_ids: set[str] = set()
        root_note_ids_by_note_id: dict[str, str] = {}
        for note_id in ordered_ids:
            root_note_id = self._resolve_root_note_id(note_id)
            root_note_ids_by_note_id[note_id] = root_note_id
            if root_note_id not in seen_root_ids:
                seen_root_ids.add(root_note_id)
                ordered_root_ids.append(root_note_id)
        total_pages = max(
            1,
            (len(ordered_root_ids) + settings.max_notes_per_page - 1)
            // settings.max_notes_per_page,
        )
        page_is_out_of_range = action.page > total_pages
        page_ids: list[str] = []
        if not page_is_out_of_range:
            page_start = (action.page - 1) * settings.max_notes_per_page
            page_end = page_start + settings.max_notes_per_page
            page_root_ids = frozenset(ordered_root_ids[page_start:page_end])
            page_ids = [
                note_id
                for note_id in ordered_ids
                if root_note_ids_by_note_id[note_id] in page_root_ids
            ]

        notes = self._build_bounded_note_payloads(
            note_ids=page_ids,
            settings=settings,
        )
        returned_character_count = sum(
            self._returned_content_length(note) for note in notes
        )
        returned_root_count = len(
            {self._required_string(note, "root_note_id") for note in notes}
        )
        has_truncated_content = any(
            self._required_bool(note, "content_is_truncated") for note in notes
        )
        has_next_page = not page_is_out_of_range and action.page < total_pages
        has_previous_page = not page_is_out_of_range and action.page > 1
        return ToolExecutionResult(
            action_name="search_notes",
            status_label="Searching notes",
            payload={
                "content_contract": {
                    "notes_are_content_bearing": True,
                    "note_content_field": "notes[].content_text",
                    "follow_up_read_required": False,
                    "instruction": (
                        "Read and synthesize notes[].content_text now. note_id is "
                        "only for citation and navigation, not a handle that "
                        "requires another read."
                    ),
                },
                "query": action.query,
                "page": action.page,
                "page_size": settings.max_notes_per_page,
                "total_pages": total_pages,
                "has_previous_page": has_previous_page,
                "previous_page": action.page - 1 if has_previous_page else 0,
                "has_next_page": has_next_page,
                "next_page": action.page + 1 if has_next_page else 0,
                "page_is_out_of_range": page_is_out_of_range,
                "matched_count": len(ordered_root_ids),
                "matched_note_count": len(ordered_ids),
                "returned_count": returned_root_count,
                "returned_note_count": len(notes),
                "returned_character_count": returned_character_count,
                "has_truncated_content": has_truncated_content,
                "max_note_characters": settings.max_note_characters,
                "max_page_characters": settings.max_page_characters,
                "notes": notes,
            },
        )

    def _ordered_matching_note_ids(
        self,
        *,
        matched_ids: set[str],
        all_note_ids: list[str],
    ) -> list[str]:
        all_note_id_set = set(all_note_ids)
        if len(all_note_id_set) != len(all_note_ids):
            raise RuntimeError("NoteStore returned duplicate note ids")
        if not matched_ids.issubset(all_note_id_set):
            raise RuntimeError("SearchIndex returned an unknown note id")

        root_ids = self._notes.get_children(None)
        traversal_stack = [
            (root_id, None) for root_id in reversed(root_ids)
        ]
        visited_note_ids: set[str] = set()
        ordered_matching_ids: list[str] = []
        while traversal_stack:
            note_id, expected_parent_id = traversal_stack.pop()
            if note_id in visited_note_ids:
                raise RuntimeError(
                    f"Hierarchy cycle or duplicate detected while ordering {note_id}"
                )
            if note_id not in all_note_id_set:
                raise RuntimeError(
                    f"Hierarchy ordering contains unknown note id {note_id}"
                )
            record = self._notes.get_note(note_id)
            if record.parent_id != expected_parent_id:
                raise RuntimeError(
                    "Hierarchy ordering parent mismatch: "
                    f"note_id={note_id} expected={expected_parent_id} "
                    f"actual={record.parent_id}"
                )
            visited_note_ids.add(note_id)
            if note_id in matched_ids:
                ordered_matching_ids.append(note_id)
            child_ids = self._notes.get_children(note_id)
            traversal_stack.extend(
                (child_id, note_id) for child_id in reversed(child_ids)
            )

        if visited_note_ids != all_note_id_set:
            missing_ids = sorted(all_note_id_set - visited_note_ids)
            raise RuntimeError(
                "Hierarchy ordering did not reach every note: "
                f"missing={missing_ids[:12]}"
            )
        return ordered_matching_ids

    def _resolve_root_note_id(self, note_id: str) -> str:
        visited: set[str] = set()
        current_note_id = note_id
        while True:
            if current_note_id in visited:
                raise RuntimeError(
                    f"Hierarchy cycle detected while grouping search result {note_id}"
                )
            visited.add(current_note_id)
            record = self._notes.get_note(current_note_id)
            if record.parent_id is None:
                return current_note_id
            if not self._notes.has_note(record.parent_id):
                raise RuntimeError(
                    "Search result hierarchy contains a missing parent: "
                    f"note_id={current_note_id} parent_id={record.parent_id}"
                )
            current_note_id = record.parent_id

    def _build_bounded_note_payloads(
        self,
        *,
        note_ids: list[str],
        settings: AgentRetrievalSettings,
    ) -> list[dict[str, object]]:
        prepared_notes: list[_PreparedNoteDisclosure] = []
        for note_id in note_ids:
            record = self._notes.get_note(note_id)
            content_text, content_is_redacted = extract_note_text_for_agent(
                content_html=record.content,
                tags=record.tags,
            )
            prepared_notes.append(
                _PreparedNoteDisclosure(
                    record=record,
                    root_note_id=self._resolve_root_note_id(note_id),
                    content_text=content_text,
                    content_is_redacted=content_is_redacted,
                )
            )
        content_limits = self._allocate_content_characters(
            prepared_notes=prepared_notes,
            settings=settings,
        )
        assert len(content_limits) == len(prepared_notes)
        return [
            self._build_note_payload(
                prepared_note=prepared_note,
                returned_character_limit=content_limits[index],
            )
            for index, prepared_note in enumerate(prepared_notes)
        ]

    @staticmethod
    def _allocate_content_characters(
        *,
        prepared_notes: list[_PreparedNoteDisclosure],
        settings: AgentRetrievalSettings,
    ) -> list[int]:
        capacities = [
            min(len(prepared_note.content_text), settings.max_note_characters)
            for prepared_note in prepared_notes
        ]
        allocated = [0 for _ in prepared_notes]
        remaining_page_characters = settings.max_page_characters
        active_indexes = [
            index for index, capacity in enumerate(capacities) if capacity > 0
        ]
        while remaining_page_characters > 0 and active_indexes:
            shared_increment = max(
                1,
                remaining_page_characters // len(active_indexes),
            )
            next_active_indexes: list[int] = []
            for index in active_indexes:
                remaining_capacity = capacities[index] - allocated[index]
                increment = min(
                    remaining_capacity,
                    shared_increment,
                    remaining_page_characters,
                )
                allocated[index] += increment
                remaining_page_characters -= increment
                if allocated[index] < capacities[index]:
                    next_active_indexes.append(index)
                if remaining_page_characters == 0:
                    next_active_indexes.extend(
                        candidate_index
                        for candidate_index in active_indexes
                        if candidate_index > index
                    )
                    break
            active_indexes = next_active_indexes
        assert sum(allocated) <= settings.max_page_characters
        assert all(
            returned_characters <= capacities[index]
            for index, returned_characters in enumerate(allocated)
        )
        return allocated

    @staticmethod
    def _build_note_payload(
        *,
        prepared_note: _PreparedNoteDisclosure,
        returned_character_limit: int,
    ) -> dict[str, object]:
        if returned_character_limit < 0:
            raise ValueError("Returned note character limit must not be negative")
        record = prepared_note.record
        content_text = prepared_note.content_text
        content_is_redacted = prepared_note.content_is_redacted
        original_character_count = len(content_text)
        content_is_truncated = original_character_count > returned_character_limit
        returned_content_text = content_text[:returned_character_limit]
        disclosed_character_count = original_character_count
        if content_is_redacted:
            disclosed_character_count = 0
        return {
            "note_id": record.id,
            "parent_id": record.parent_id or "",
            "root_note_id": prepared_note.root_note_id,
            "content_text": returned_content_text,
            "content_character_count": disclosed_character_count,
            "returned_character_count": len(returned_content_text),
            "content_is_truncated": content_is_truncated,
            "content_is_redacted": content_is_redacted,
            "tags": record.tags,
            "created_at": ReadOnlyAgentToolRegistry._timestamp_text(record.created_at),
            "updated_at": ReadOnlyAgentToolRegistry._timestamp_text(record.updated_at),
        }

    @staticmethod
    def _timestamp_text(value: datetime | None) -> str:
        if value is None:
            return ""
        if not isinstance(value, datetime):
            raise TypeError(f"Note timestamp must be datetime or None, got {type(value)}")
        return value.isoformat()

    @staticmethod
    def _required_string(payload: dict[str, object], key: str) -> str:
        value = payload[key]
        assert isinstance(value, str)
        return value

    @staticmethod
    def _required_bool(payload: dict[str, object], key: str) -> bool:
        value = payload[key]
        assert isinstance(value, bool)
        return value

    @staticmethod
    def _returned_content_length(payload: dict[str, object]) -> int:
        value = payload["returned_character_count"]
        assert isinstance(value, int) and not isinstance(value, bool)
        assert value >= 0
        return value

    def _read_notes_by_id(
        self,
        action: ReadNotesByIdAction,
        *,
        settings: AgentRetrievalSettings,
    ) -> ToolExecutionResult:
        found_note_ids = []
        missing_note_ids = []
        for note_id in action.note_ids:
            if not self._notes.has_note(note_id):
                missing_note_ids.append(note_id)
                continue
            found_note_ids.append(note_id)
        notes = self._build_bounded_note_payloads(
            note_ids=found_note_ids,
            settings=settings,
        )
        total_characters = sum(
            self._returned_content_length(note) for note in notes
        )
        count = len(notes)
        noun = "notes"
        if count == 1:
            noun = "note"
        return ToolExecutionResult(
            action_name="read_notes_by_id",
            status_label=f"Reading {count} {noun} by ID",
            payload={
                "notes": notes,
                "missing_note_ids": missing_note_ids,
                "returned_character_count": total_characters,
                "max_note_characters": settings.max_note_characters,
                "max_page_characters": settings.max_page_characters,
                "has_truncated_content": any(
                    self._required_bool(note, "content_is_truncated")
                    for note in notes
                ),
            },
        )


read_only_agent_tools = ReadOnlyAgentToolRegistry(notes=note_store, searches=search_index)
