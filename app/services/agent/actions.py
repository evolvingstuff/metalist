"""Typed actions available to the read-only agent runtime."""

from __future__ import annotations

from typing import Annotated, Literal, Self, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from app.services.search_query import parse_search_query


def _validate_agent_search_query(value: str) -> str:
    if value.strip() == "":
        raise ValueError("Agent search query must not be blank")
    if len(value) > 1_000:
        raise ValueError("Agent search query must not exceed 1000 characters")
    parsed = parse_search_query(value)
    for clause in parsed.clauses:
        if len(clause.required_tags) == 0 and len(clause.required_text) == 0:
            raise ValueError(
                "Every agent search clause must contain at least one positive term"
            )
    return value


class SearchNotesAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["search_notes"]
    query: str = Field(..., min_length=1, max_length=1_000)
    page: int = Field(
        ...,
        description="The one-based page of matching notes to retrieve.",
    )
    rationale: str = Field(..., min_length=1, max_length=2_000)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        return _validate_agent_search_query(value)

    @field_validator("page")
    @classmethod
    def validate_page(cls, value: int) -> int:
        if value < 1 or value > 100_000:
            raise ValueError("Agent search page must be from 1 to 100000")
        return value

    @field_validator("rationale")
    @classmethod
    def reject_blank_rationale(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Agent action rationale must not be blank")
        return value


class ReadNotesByIdAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["read_notes_by_id"]
    note_ids: list[str] = Field(..., min_length=1, max_length=12)
    rationale: str = Field(..., min_length=1, max_length=2_000)

    @field_validator("note_ids")
    @classmethod
    def validate_note_ids(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or value.strip() == "" for value in values):
            raise ValueError("read_notes_by_id note ids must be non-empty strings")
        normalized = [value.strip() for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("read_notes_by_id note ids must be unique")
        return normalized

    @field_validator("rationale")
    @classmethod
    def reject_blank_rationale(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Agent action rationale must not be blank")
        return value


class RespondAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["respond"]
    basis: str = Field(..., min_length=1, max_length=4_000)

    @field_validator("basis")
    @classmethod
    def reject_blank_basis(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Agent response basis must not be blank")
        return value


class SearchNotesIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["search_notes"]
    rationale: str = Field(..., min_length=1, max_length=4_000)

    @field_validator("rationale")
    @classmethod
    def reject_blank_rationale(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Agent action rationale must not be blank")
        return value


AgentAction = Annotated[
    Union[SearchNotesAction, ReadNotesByIdAction, RespondAction],
    Field(discriminator="kind"),
]

agent_action_adapter: TypeAdapter[AgentAction] = TypeAdapter(AgentAction)


AgentRouteAction = Annotated[
    Union[SearchNotesIntent, ReadNotesByIdAction, RespondAction],
    Field(discriminator="kind"),
]


class AgentRouteEnvelope(BaseModel):
    """Flat action-routing schema with no root unions or references."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["respond", "search_notes", "read_notes_by_id"] = Field(
        ...,
        description=(
            "The single next action. respond answers without note retrieval; "
            "search_notes searches the note index and returns content-bearing "
            "matching notes in notes[].content_text, not ID-only previews; "
            "read_notes_by_id retrieves bounded content from notes whose ids are "
            "already known without performing a search."
        ),
    )
    note_ids: list[str] = Field(
        ...,
        max_length=12,
        description=(
            "Note UUIDs used only by read_notes_by_id; required but ignored otherwise."
        ),
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=4_000,
        description=(
            "Why this is the correct next action; never empty. After search_notes, "
            "read and synthesize the returned notes[].content_text directly. Do not "
            "search again or read by ID merely to obtain details already present "
            "there. A repeat search reason must name concrete missing evidence or a "
            "specific false-positive pattern."
        ),
    )

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        if self.kind == "read_notes_by_id":
            self._validate_read_fields()
        else:
            assert self.kind in {"respond", "search_notes"}
        return self

    def to_action(self) -> AgentRouteAction:
        if self.kind == "search_notes":
            return SearchNotesIntent(
                kind=self.kind,
                rationale=self.reason,
            )
        if self.kind == "read_notes_by_id":
            return ReadNotesByIdAction(
                kind=self.kind,
                note_ids=self.note_ids,
                rationale=self.reason,
            )
        assert self.kind == "respond"
        return RespondAction(kind=self.kind, basis=self.reason)

    def _validate_read_fields(self) -> None:
        if len(self.note_ids) == 0:
            raise ValueError("read_notes_by_id requires at least one note id")
        normalized_note_ids = [note_id.strip() for note_id in self.note_ids]
        if any(note_id == "" for note_id in normalized_note_ids):
            raise ValueError("read_notes_by_id note ids must be non-empty strings")
        if len(set(normalized_note_ids)) != len(normalized_note_ids):
            raise ValueError("read_notes_by_id note ids must be unique")
agent_route_envelope_adapter: TypeAdapter[AgentRouteEnvelope] = TypeAdapter(
    AgentRouteEnvelope
)


class SearchQueryEnvelope(BaseModel):
    """Structured search query generated while the Search skill is active."""

    model_config = ConfigDict(extra="forbid")

    search_query: str = Field(
        ...,
        description=(
            "The focused MetaList query for the current user request. Earlier "
            "conversation topics must not become positive or negative query terms "
            "unless the current request explicitly depends on them. For a broad "
            "topic, cover both its tag and exact-text forms in the first query, such "
            "as foo OR \"foo\"."
        ),
    )
    page: int = Field(
        ...,
        description=(
            "The one-based result page. Use 1 for a new or refined query. Use the "
            "next_page value from a prior result only when more results are needed."
        ),
    )
    reason: str = Field(
        ...,
        description="Why this is the focused search query to execute; never empty.",
    )

    @field_validator("search_query")
    @classmethod
    def validate_search_query(cls, value: str) -> str:
        return _validate_agent_search_query(value)

    @field_validator("page")
    @classmethod
    def validate_page(cls, value: int) -> int:
        if value < 1 or value > 100_000:
            raise ValueError("Search result page must be from 1 to 100000")
        return value

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Search query reason must not be blank")
        if len(value) > 2_000:
            raise ValueError("Search query reason must not exceed 2000 characters")
        return value

    def to_action(self) -> SearchNotesAction:
        return SearchNotesAction(
            kind="search_notes",
            query=self.search_query,
            page=self.page,
            rationale=self.reason,
        )


search_query_envelope_adapter: TypeAdapter[SearchQueryEnvelope] = TypeAdapter(
    SearchQueryEnvelope
)


def agent_route_response_schema() -> dict[str, object]:
    schema = AgentRouteEnvelope.model_json_schema()
    assert schema["type"] == "object"
    return schema


def parse_agent_route_json(response_content: str) -> AgentRouteAction:
    envelope = agent_route_envelope_adapter.validate_json(response_content)
    return envelope.to_action()


def parse_search_query_json(response_content: str) -> SearchNotesAction:
    envelope = search_query_envelope_adapter.validate_json(response_content)
    return envelope.to_action()
