"""Read-only PKMS-domain tools exposed to the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.services.agent.actions import ReadNotesAction
from app.services.agent.actions import SearchNotesAction
from app.services.note_store import NoteStore
from app.services.note_store import store as note_store
from app.services.search_index import SearchIndex
from app.services.search_index import search_index
from app.utils.text_utils import strip_html


_MAX_SEARCH_RESULTS = 20
_MAX_SEARCH_PREVIEW_CHARACTERS = 400
_MAX_READ_NOTE_CHARACTERS = 12_000
_MAX_READ_TOTAL_CHARACTERS = 60_000


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


class ReadOnlyAgentToolRegistry:
    def __init__(self, *, notes: NoteStore, searches: SearchIndex) -> None:
        self._notes = notes
        self._searches = searches

    def spec_for(self, action: object) -> ToolSpec:
        if isinstance(action, SearchNotesAction):
            return ToolSpec(
                name="search_notes",
                description="Search the in-memory MetaList note index",
                mutates=False,
                permission=ToolPermission.READ,
            )
        if isinstance(action, ReadNotesAction):
            return ToolSpec(
                name="read_notes",
                description="Read selected notes from the in-memory MetaList store",
                mutates=False,
                permission=ToolPermission.READ,
            )
        raise TypeError(f"No tool corresponds to action type {type(action).__name__}")

    def execute(self, action: object) -> ToolExecutionResult:
        if isinstance(action, SearchNotesAction):
            return self._search_notes(action)
        if isinstance(action, ReadNotesAction):
            return self._read_notes(action)
        raise TypeError(f"Cannot execute action type {type(action).__name__}")

    def _search_notes(self, action: SearchNotesAction) -> ToolExecutionResult:
        matched_ids = self._searches.query_note_ids(action.query)
        ordered_ids = [
            note_id for note_id in self._notes.list_note_ids() if note_id in matched_ids
        ]
        returned_ids = ordered_ids[:_MAX_SEARCH_RESULTS]
        results = []
        for note_id in returned_ids:
            record = self._notes.get_note(note_id)
            content_text = strip_html(record.content).strip()
            results.append(
                {
                    "note_id": record.id,
                    "parent_id": record.parent_id or "",
                    "content_preview": content_text[:_MAX_SEARCH_PREVIEW_CHARACTERS],
                    "tags": record.tags,
                }
            )
        return ToolExecutionResult(
            action_name="search_notes",
            status_label="Searching notes",
            payload={
                "query": action.query,
                "matched_count": len(ordered_ids),
                "returned_count": len(results),
                "is_truncated": len(ordered_ids) > len(results),
                "notes": results,
            },
        )

    def _read_notes(self, action: ReadNotesAction) -> ToolExecutionResult:
        notes = []
        missing_note_ids = []
        omitted_note_ids = []
        total_characters = 0
        for note_id in action.note_ids:
            if not self._notes.has_note(note_id):
                missing_note_ids.append(note_id)
                continue
            record = self._notes.get_note(note_id)
            content_text = strip_html(record.content).strip()
            bounded_text = content_text[:_MAX_READ_NOTE_CHARACTERS]
            if total_characters + len(bounded_text) > _MAX_READ_TOTAL_CHARACTERS:
                omitted_note_ids.append(note_id)
                continue
            total_characters += len(bounded_text)
            notes.append(
                {
                    "note_id": record.id,
                    "parent_id": record.parent_id or "",
                    "content_text": bounded_text,
                    "content_is_truncated": len(content_text) > len(bounded_text),
                    "tags": record.tags,
                }
            )
        count = len(notes)
        noun = "notes"
        if count == 1:
            noun = "note"
        return ToolExecutionResult(
            action_name="read_notes",
            status_label=f"Reading {count} {noun}",
            payload={
                "notes": notes,
                "missing_note_ids": missing_note_ids,
                "omitted_note_ids": omitted_note_ids,
                "returned_character_count": total_characters,
            },
        )


read_only_agent_tools = ReadOnlyAgentToolRegistry(notes=note_store, searches=search_index)
