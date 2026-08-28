"""Typed actions available to the read-only agent runtime."""

from __future__ import annotations

from typing import Annotated, Literal, Self, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from app.services.search_query import parse_search_query


class SearchNotesAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["search_notes"]
    query: str = Field(..., min_length=1, max_length=1_000)
    rationale: str = Field(..., min_length=1, max_length=2_000)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Agent search query must not be blank")
        parse_search_query(value)
        return value

    @field_validator("rationale")
    @classmethod
    def reject_blank_rationale(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Agent action rationale must not be blank")
        return value


class ReadNotesAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["read_notes"]
    note_ids: list[str] = Field(..., min_length=1, max_length=12)
    rationale: str = Field(..., min_length=1, max_length=2_000)

    @field_validator("note_ids")
    @classmethod
    def validate_note_ids(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or value.strip() == "" for value in values):
            raise ValueError("read_notes note ids must be non-empty strings")
        normalized = [value.strip() for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("read_notes note ids must be unique")
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


AgentAction = Annotated[
    Union[SearchNotesAction, ReadNotesAction, RespondAction],
    Field(discriminator="kind"),
]

agent_action_adapter: TypeAdapter[AgentAction] = TypeAdapter(AgentAction)


class AgentActionEnvelope(BaseModel):
    """Flat Ollama wire schema with no root unions or references."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "kind": "search_notes",
                    "search_query": '"project deadline"',
                    "note_ids": [],
                    "reason": "Find notes containing the requested deadline.",
                },
                {
                    "kind": "read_notes",
                    "search_query": "",
                    "note_ids": ["note-uuid"],
                    "reason": "Read the relevant search result before answering.",
                },
                {
                    "kind": "respond",
                    "search_query": "",
                    "note_ids": [],
                    "reason": "The greeting can be answered without reading notes.",
                },
            ]
        },
    )

    kind: Literal["search_notes", "read_notes", "respond"] = Field(
        ...,
        description="The single next action to take.",
    )
    search_query: str = Field(
        ...,
        max_length=1_000,
        description="MetaList query used by search_notes; required but ignored otherwise.",
    )
    note_ids: list[str] = Field(
        ...,
        max_length=12,
        description="Note UUIDs used by read_notes; required but ignored otherwise.",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=4_000,
        description="Why this is the correct next action; never empty.",
    )

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        if self.kind == "search_notes":
            self._validate_search_fields()
        elif self.kind == "read_notes":
            self._validate_read_fields()
        else:
            assert self.kind == "respond"
        return self

    def to_action(self) -> AgentAction:
        if self.kind == "search_notes":
            return SearchNotesAction(
                kind=self.kind,
                query=self.search_query,
                rationale=self.reason,
            )
        if self.kind == "read_notes":
            return ReadNotesAction(
                kind=self.kind,
                note_ids=self.note_ids,
                rationale=self.reason,
            )
        assert self.kind == "respond"
        return RespondAction(kind=self.kind, basis=self.reason)

    def _validate_search_fields(self) -> None:
        if self.search_query.strip() == "":
            raise ValueError("search_notes requires a non-blank search_query")
        parse_search_query(self.search_query)

    def _validate_read_fields(self) -> None:
        if len(self.note_ids) == 0:
            raise ValueError("read_notes requires at least one note id")
        normalized_note_ids = [note_id.strip() for note_id in self.note_ids]
        if any(note_id == "" for note_id in normalized_note_ids):
            raise ValueError("read_notes note ids must be non-empty strings")
        if len(set(normalized_note_ids)) != len(normalized_note_ids):
            raise ValueError("read_notes note ids must be unique")
agent_action_envelope_adapter: TypeAdapter[AgentActionEnvelope] = TypeAdapter(
    AgentActionEnvelope
)


def agent_action_response_schema() -> dict[str, object]:
    schema = AgentActionEnvelope.model_json_schema()
    assert schema["type"] == "object"
    return schema


def parse_agent_action_json(response_content: str) -> AgentAction:
    envelope = agent_action_envelope_adapter.validate_json(response_content)
    return envelope.to_action()
