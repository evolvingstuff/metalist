"""Typed actions available to the read-only agent runtime."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator
from typing_extensions import Self

from app.services.search_query import parse_search_query
from app.services.agent.help_catalog import HelpTopic


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
    rationale: str = Field(..., min_length=1, max_length=2_000)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        return _validate_agent_search_query(value)

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


class OpenWebPagesAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["open_web_pages"]
    urls: list[str] = Field(..., min_length=1, max_length=8)
    rationale: str = Field(..., min_length=1, max_length=2_000)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(value == "" for value in normalized):
            raise ValueError("Web page URLs must be non-empty strings")
        return normalized

    @field_validator("rationale")
    @classmethod
    def reject_blank_rationale(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Agent action rationale must not be blank")
        return value


class ContextualWebActionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["respond", "open_web_pages"]
    urls: list[str] = Field(..., max_length=8)
    reason: str = Field(..., min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        if self.kind == "open_web_pages" and len(self.urls) == 0:
            raise ValueError("open_web_pages requires at least one URL")
        if self.kind == "respond" and len(self.urls) != 0:
            raise ValueError("respond requires an empty URL list")
        OpenWebPagesAction.validate_urls(self.urls) if self.urls else self.urls
        return self

    def to_action(self) -> RespondAction | OpenWebPagesAction:
        if self.kind == "open_web_pages":
            return OpenWebPagesAction(
                kind=self.kind,
                urls=self.urls,
                rationale=self.reason,
            )
        return RespondAction(kind="respond", basis=self.reason)


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


class ScopedRouteEnvelope(BaseModel):
    """High-level route for the user-bounded investigation architecture."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["respond", "investigate_current_scope", "tag_proposals", "metalist_help"] = Field(
        ...,
        description=(
            "metalist_help for MetaList product questions or opening menus, with relevant help_topics; "
            "respond for requests answerable from the supplied selected note tree alone or without note evidence; "
            "investigate_current_scope only when the answer depends on evidence "
            "inside the frozen active MetaList result scope. "
            "tag_proposals ONLY for an explicit current user request to generate, "
            "accept, reject, or remove tag proposals. Questions about tagging, "
            "hypotheticals, and unrelated requests must never select tag_proposals."
        ),
    )
    help_topics: list[HelpTopic] = Field(..., max_length=10, description="Relevant product-help topics for metalist_help; empty for other routes.")

    @model_validator(mode="after")
    def validate_help_topics(self) -> Self:
        if len(set(self.help_topics)) != len(self.help_topics):
            raise ValueError("Help topics must be unique")
        if (self.kind == "metalist_help") != bool(self.help_topics):
            raise ValueError("Only metalist_help requires nonempty help_topics")
        return self

    reason: str = Field(..., min_length=1, max_length=4_000)

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Scoped route reason must not be blank")
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

    kind: Literal["respond", "search_notes", "read_notes_by_id"]
    note_ids: list[str] = Field(..., max_length=12)
    reason: str = Field(..., min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        if self.kind == "read_notes_by_id":
            if len(self.note_ids) == 0:
                raise ValueError("read_notes_by_id requires at least one note id")
            normalized = [note_id.strip() for note_id in self.note_ids]
            if any(note_id == "" for note_id in normalized):
                raise ValueError("read_notes_by_id note ids must be non-empty strings")
            if len(set(normalized)) != len(normalized):
                raise ValueError("read_notes_by_id note ids must be unique")
        return self

    def to_action(self) -> AgentRouteAction:
        if self.kind == "search_notes":
            return SearchNotesIntent(kind=self.kind, rationale=self.reason)
        if self.kind == "read_notes_by_id":
            return ReadNotesByIdAction(
                kind=self.kind,
                note_ids=self.note_ids,
                rationale=self.reason,
            )
        assert self.kind == "respond"
        return RespondAction(kind=self.kind, basis=self.reason)


agent_route_envelope_adapter: TypeAdapter[AgentRouteEnvelope] = TypeAdapter(
    AgentRouteEnvelope
)


class SearchQueryEnvelope(BaseModel):
    """Structured single-payload search query generated by the Search skill."""

    model_config = ConfigDict(extra="forbid")

    search_query: str = Field(..., description="The focused MetaList query.")
    reason: str = Field(..., min_length=1, max_length=2_000)

    @field_validator("search_query")
    @classmethod
    def validate_search_query(cls, value: str) -> str:
        return _validate_agent_search_query(value)

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Search query reason must not be blank")
        return value

    def to_action(self) -> SearchNotesAction:
        return SearchNotesAction(
            kind="search_notes",
            query=self.search_query,
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
