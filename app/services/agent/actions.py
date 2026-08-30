"""Typed actions available to the read-only agent runtime."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Annotated, Literal, Self, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    TypeAdapter,
    field_validator,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from app.services.search_query import parse_search_query


@dataclass(frozen=True, slots=True)
class InvestigationStepConstraints:
    has_next_note_page: bool
    requires_complete_scope_coverage: bool
    current_facet_page: int
    total_facet_pages: int
    disclosed_tags: frozenset[str]
    disclosed_state_ids: frozenset[str]
    observed_source_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.has_next_note_page, bool):
            raise TypeError("has_next_note_page must be bool")
        if not isinstance(self.requires_complete_scope_coverage, bool):
            raise TypeError("requires_complete_scope_coverage must be bool")
        if self.current_facet_page < 1:
            raise ValueError("current_facet_page must be positive")
        if self.total_facet_pages < 1:
            raise ValueError("total_facet_pages must be positive")
        if self.current_facet_page > self.total_facet_pages:
            raise ValueError("current_facet_page exceeds total_facet_pages")


@dataclass(frozen=True, slots=True)
class ScopedRouteConstraints:
    explicit_saved_notes_request: bool

    def __post_init__(self) -> None:
        if not isinstance(self.explicit_saved_notes_request, bool):
            raise TypeError("explicit_saved_notes_request must be bool")


@dataclass(frozen=True, slots=True)
class EvidenceSelectionConstraints:
    allowed_note_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_note_ids, frozenset):
            raise TypeError("allowed_note_ids must be a frozenset")
        if any(
            not isinstance(note_id, str) or note_id == ""
            for note_id in self.allowed_note_ids
        ):
            raise ValueError("allowed_note_ids must contain non-empty strings")


_INVESTIGATION_STEP_CONSTRAINTS: ContextVar[
    InvestigationStepConstraints | None
] = ContextVar("investigation_step_constraints", default=None)
_SCOPED_ROUTE_CONSTRAINTS: ContextVar[ScopedRouteConstraints | None] = ContextVar(
    "scoped_route_constraints",
    default=None,
)
_EVIDENCE_SELECTION_CONSTRAINTS: ContextVar[
    EvidenceSelectionConstraints | None
] = ContextVar("evidence_selection_constraints", default=None)

_EXPLICIT_SAVED_NOTES_PATTERNS = (
    re.compile(r"\b(?:my|our)\s+(?:saved\s+)?notes?\b", re.IGNORECASE),
    re.compile(
        r"\b(?:summari[sz]e|search|find|review|read|inspect|analy[sz]e|"
        r"synthesi[sz]e)\b(?:\W+\w+){0,12}\W+notes?\b",
        re.IGNORECASE,
    ),
)
_SAVED_NOTES_EXCLUSION_PATTERN = re.compile(
    r"\b(?:without|do\s+not|don't|dont)\b.{0,48}"
    r"\b(?:use|using|search|read|consult|reference)\b.{0,48}"
    r"\b(?:my|our)?\s*(?:saved\s+)?notes?\b",
    re.IGNORECASE,
)


def request_explicitly_requires_saved_notes(user_message: str) -> bool:
    if not isinstance(user_message, str):
        raise TypeError("user_message must be a string")
    if user_message.strip() == "":
        raise ValueError("user_message must not be blank")
    if _SAVED_NOTES_EXCLUSION_PATTERN.search(user_message) is not None:
        return False
    return any(
        pattern.search(user_message) is not None
        for pattern in _EXPLICIT_SAVED_NOTES_PATTERNS
    )


def request_requires_complete_scope_coverage(user_message: str) -> bool:
    if not isinstance(user_message, str):
        raise TypeError("user_message must be a string")
    if user_message.strip() == "":
        raise ValueError("user_message must not be blank")
    folded = user_message.casefold()
    complete_markers = (
        "all of my",
        "all of our",
        "all of the",
        "everything",
        "every note",
        "entire scope",
        "entire set",
        "exhaustive",
    )
    return any(marker in folded for marker in complete_markers)


@contextmanager
def bind_investigation_step_constraints(
    constraints: InvestigationStepConstraints,
) -> Iterator[None]:
    if not isinstance(constraints, InvestigationStepConstraints):
        raise TypeError("constraints must be InvestigationStepConstraints")
    token = _INVESTIGATION_STEP_CONSTRAINTS.set(constraints)
    try:
        yield
    finally:
        _INVESTIGATION_STEP_CONSTRAINTS.reset(token)


@contextmanager
def bind_scoped_route_constraints(
    constraints: ScopedRouteConstraints,
) -> Iterator[None]:
    if not isinstance(constraints, ScopedRouteConstraints):
        raise TypeError("constraints must be ScopedRouteConstraints")
    token = _SCOPED_ROUTE_CONSTRAINTS.set(constraints)
    try:
        yield
    finally:
        _SCOPED_ROUTE_CONSTRAINTS.reset(token)


@contextmanager
def bind_evidence_selection_constraints(
    constraints: EvidenceSelectionConstraints,
) -> Iterator[None]:
    if not isinstance(constraints, EvidenceSelectionConstraints):
        raise TypeError("constraints must be EvidenceSelectionConstraints")
    token = _EVIDENCE_SELECTION_CONSTRAINTS.set(constraints)
    try:
        yield
    finally:
        _EVIDENCE_SELECTION_CONSTRAINTS.reset(token)


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


class ScopedRouteEnvelope(BaseModel):
    """High-level route for the user-bounded investigation architecture."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["respond", "investigate_current_scope"] = Field(
        ...,
        description=(
            "respond for requests answerable without the user's notes; "
            "investigate_current_scope only when the answer depends on evidence "
            "inside the frozen active MetaList result scope."
        ),
    )
    reason: str = Field(..., min_length=1, max_length=4_000)

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Scoped route reason must not be blank")
        return value

    @model_validator(mode="after")
    def enforce_explicit_saved_notes_request(self) -> Self:
        constraints = _SCOPED_ROUTE_CONSTRAINTS.get()
        if (
            constraints is not None
            and constraints.explicit_saved_notes_request
            and self.kind != "investigate_current_scope"
        ):
            raise ValueError(
                "The user explicitly requests evidence from saved notes; choose "
                "investigate_current_scope, not respond"
            )
        return self


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


def _without_max_length_keywords(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_max_length_keywords(child)
            for key, child in value.items()
            if key != "maxLength"
        }
    if isinstance(value, list):
        return [_without_max_length_keywords(child) for child in value]
    return value


class _OllamaCompatibleSchemaModel(BaseModel):
    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        compatible_schema = _without_max_length_keywords(schema)
        if not isinstance(compatible_schema, dict):
            raise TypeError("Pydantic model JSON schema must be an object")
        return compatible_schema


class WorkingEvidence(_OllamaCompatibleSchemaModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(..., min_length=1, max_length=2_000)
    source_ids: list[str] = Field(..., min_length=1, max_length=4)

    @field_validator("claim")
    @classmethod
    def reject_blank_claim(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Working evidence claim must not be blank")
        return value

    @field_validator("source_ids")
    @classmethod
    def validate_source_ids(cls, values: list[str]) -> list[str]:
        return _validate_unique_nonempty_ids(values, label="Working evidence source ids")


class WorkingSummary(_OllamaCompatibleSchemaModel):
    model_config = ConfigDict(extra="forbid")

    answer_relevant_facts: list[WorkingEvidence] = Field(..., max_length=4)
    possible_conclusions: list[WorkingEvidence] = Field(..., max_length=2)
    contradictions_or_uncertainties: list[WorkingEvidence] = Field(..., max_length=2)
    unresolved_questions: list[str] = Field(..., max_length=4)
    useful_search_terms_or_tags: list[str] = Field(..., max_length=6)

    @field_validator("unresolved_questions", "useful_search_terms_or_tags")
    @classmethod
    def validate_text_list(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or value.strip() == "" for value in values):
            raise ValueError("Working-summary text entries must be non-empty strings")
        if any(len(value) > 2_000 for value in values):
            raise ValueError("Working-summary text entries must not exceed 2000 characters")
        if len(set(values)) != len(values):
            raise ValueError("Working-summary text entries must be unique")
        return values

    def referenced_source_ids(self) -> frozenset[str]:
        return frozenset(
            source_id
            for collection in (
                self.answer_relevant_facts,
                self.possible_conclusions,
                self.contradictions_or_uncertainties,
            )
            for evidence in collection
            for source_id in evidence.source_ids
        )


class _EvidenceSelectionBase(_OllamaCompatibleSchemaModel):
    """Validated evidence IDs shared by both selection response modes."""

    model_config = ConfigDict(extra="forbid")

    relevant_note_ids: list[str] = Field(..., max_length=12)

    @field_validator("relevant_note_ids")
    @classmethod
    def validate_relevant_note_ids(cls, values: list[str]) -> list[str]:
        return _validate_unique_nonempty_ids(values, label="Relevant evidence ids")

    @model_validator(mode="after")
    def validate_run_constraints(self) -> Self:
        constraints = _EVIDENCE_SELECTION_CONSTRAINTS.get()
        if constraints is not None and not set(self.relevant_note_ids).issubset(
            constraints.allowed_note_ids
        ):
            raise ValueError("Relevant evidence ids must come from the current page")
        return self


class EvidenceSelection(_EvidenceSelectionBase):
    """Development evidence selection with a required model rationale."""

    reason: str = Field(..., min_length=1, max_length=2_000)


class EvidenceSelectionWithoutRationale(_EvidenceSelectionBase):
    """Compact evidence selection containing only exact relevant note IDs."""


class InvestigationStep(_OllamaCompatibleSchemaModel):
    """Flat Ollama wire schema for summary replacement plus one next action."""

    model_config = ConfigDict(extra="forbid")

    action_kind: Literal[
        "page_next",
        "refine_tags",
        "refine_exact_text",
        "inspect_tag_facets",
        "backtrack",
        "reopen_sources",
        "answer",
    ]
    tag_expression: str = Field(
        ...,
        max_length=1_000,
        description="Used only for refine_tags; emit an empty string otherwise.",
    )
    exact_text: str = Field(
        ...,
        max_length=1_000,
        description="Used only for refine_exact_text; emit an empty string otherwise.",
    )
    facet_page: int = Field(
        ...,
        ge=0,
        le=100_000,
        description="Used only for inspect_tag_facets; emit 0 otherwise.",
    )
    backtrack_state_id: str = Field(
        ...,
        max_length=128,
        description="Used only for backtrack; emit an empty string otherwise.",
    )
    source_ids: list[str] = Field(
        ...,
        max_length=12,
        description="Used only for reopen_sources; emit an empty array otherwise.",
    )
    answer_source_ids: list[str] = Field(
        ...,
        max_length=32,
        description=(
            "Used only for answer; include at most 32 observed authoritative "
            "sources and emit an empty array otherwise."
        ),
    )
    reason: str = Field(..., min_length=1, max_length=2_000)
    evidence_sufficiency: Literal[
        "insufficient",
        "sufficient",
        "sufficient_with_uncertainty",
    ]
    working_summary: WorkingSummary

    @model_validator(mode="before")
    @classmethod
    def normalize_inactive_action_arguments(cls, value: object) -> object:
        if not isinstance(value, dict) or "action_kind" not in value:
            return value
        action_fields = {
            "tag_expression",
            "exact_text",
            "facet_page",
            "backtrack_state_id",
            "source_ids",
            "answer_source_ids",
        }
        if not action_fields.issubset(value):
            return value
        active_field_by_kind = {
            "page_next": "",
            "refine_tags": "tag_expression",
            "refine_exact_text": "exact_text",
            "inspect_tag_facets": "facet_page",
            "backtrack": "backtrack_state_id",
            "reopen_sources": "source_ids",
            "answer": "answer_source_ids",
        }
        action_kind = value["action_kind"]
        if not isinstance(action_kind, str):
            return value
        if action_kind not in active_field_by_kind:
            return value
        normalized = dict(value)
        active_field = active_field_by_kind[action_kind]
        for field_name in action_fields:
            if field_name == active_field:
                continue
            if field_name in {"source_ids", "answer_source_ids"}:
                normalized[field_name] = []
            elif field_name == "facet_page":
                normalized[field_name] = 0
            else:
                normalized[field_name] = ""
        return normalized

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Investigation action reason must not be blank")
        return value

    @field_validator("source_ids", "answer_source_ids")
    @classmethod
    def validate_step_source_ids(cls, values: list[str]) -> list[str]:
        return _validate_unique_nonempty_ids(values, label="Investigation source ids")

    @model_validator(mode="after")
    def validate_action_arguments(self) -> Self:
        if self.action_kind == "refine_tags":
            self._require_only(active_field="tag_expression")
        elif self.action_kind == "refine_exact_text":
            self._require_only(active_field="exact_text")
        elif self.action_kind == "inspect_tag_facets":
            self._require_only(active_field="facet_page")
        elif self.action_kind == "backtrack":
            self._require_only(active_field="backtrack_state_id")
        elif self.action_kind == "reopen_sources":
            self._require_only(active_field="source_ids")
        elif self.action_kind == "answer":
            if (
                self.tag_expression != ""
                or self.exact_text != ""
                or self.facet_page != 0
                or self.backtrack_state_id != ""
                or len(self.source_ids) != 0
            ):
                raise ValueError(
                    "answer requires only answer_source_ids; set tag_expression, "
                    "exact_text, and backtrack_state_id to empty strings, facet_page "
                    "to 0, and source_ids to an empty array"
                )
            if self.evidence_sufficiency == "insufficient":
                raise ValueError("answer requires sufficient evidence")
        else:
            assert self.action_kind == "page_next"
            self._require_only(active_field="")
        constraints = _INVESTIGATION_STEP_CONSTRAINTS.get()
        if constraints is not None:
            self._validate_run_constraints(constraints)
        return self

    def _validate_run_constraints(
        self,
        constraints: InvestigationStepConstraints,
    ) -> None:
        if self.action_kind == "page_next" and not constraints.has_next_note_page:
            raise ValueError("Current subset has no next note page")
        if self.action_kind == "inspect_tag_facets":
            if self.facet_page > constraints.total_facet_pages:
                raise ValueError("Requested facet page is out of range")
            if self.facet_page == constraints.current_facet_page:
                raise ValueError("Requested facet page is already current")
        if self.action_kind == "backtrack":
            if self.backtrack_state_id not in constraints.disclosed_state_ids:
                raise ValueError("Backtrack target has not been disclosed")
        if self.action_kind == "reopen_sources":
            if not set(self.source_ids).issubset(constraints.observed_source_ids):
                raise ValueError("Sources must have been previously observed")
        if self.action_kind == "answer":
            if not set(self.answer_source_ids).issubset(
                constraints.observed_source_ids
            ):
                raise ValueError("Answer sources must have been previously observed")
            if (
                constraints.requires_complete_scope_coverage
                and constraints.has_next_note_page
            ):
                raise ValueError(
                    "Complete-scope request cannot answer while an evidence page remains"
                )
        if self.action_kind == "refine_tags":
            parsed = parse_search_query(self.tag_expression)
            referenced_tags: set[str] = set()
            for clause in parsed.clauses:
                if clause.required_text or clause.forbidden_text:
                    raise ValueError("Tag refinement cannot contain quoted text")
                referenced_tags.update(
                    tag.casefold() for tag in clause.required_tags
                )
                referenced_tags.update(
                    tag.casefold() for tag in clause.forbidden_tags
                )
            if not referenced_tags:
                raise ValueError("Tag refinement must contain a tag")
            if not referenced_tags.issubset(constraints.disclosed_tags):
                raise ValueError("Tag refinement contains an undisclosed tag")

    def _require_only(
        self,
        *,
        active_field: str,
    ) -> None:
        allowed_fields = {
            "",
            "tag_expression",
            "exact_text",
            "facet_page",
            "backtrack_state_id",
            "source_ids",
            "answer_source_ids",
        }
        if active_field not in allowed_fields:
            raise ValueError("Unknown active investigation argument field")
        fields_are_active = {
            "tag_expression": self.tag_expression != "",
            "exact_text": self.exact_text != "",
            "facet_page": self.facet_page != 0,
            "backtrack_state_id": self.backtrack_state_id != "",
            "source_ids": len(self.source_ids) != 0,
            "answer_source_ids": len(self.answer_source_ids) != 0,
        }
        expected = {
            field_name: field_name == active_field
            for field_name in fields_are_active
        }
        if fields_are_active != expected:
            raise ValueError(f"{self.action_kind} requires only {self._expected_argument_label(expected)}")

    @staticmethod
    def _expected_argument_label(expected: dict[str, bool]) -> str:
        names = [name for name, is_expected in expected.items() if is_expected]
        if not names:
            return "empty action arguments"
        return " and ".join(names)


def _validate_unique_nonempty_ids(values: list[str], *, label: str) -> list[str]:
    if any(not isinstance(value, str) or value.strip() == "" for value in values):
        raise ValueError(f"{label} must be non-empty strings")
    normalized = [value.strip() for value in values]
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique")
    return normalized


def validate_working_summary_for_observed_sources(
    *,
    summary: WorkingSummary,
    observed_source_ids: frozenset[str],
    maximum_characters: int,
) -> None:
    if not isinstance(summary, WorkingSummary):
        raise TypeError("summary must be WorkingSummary")
    if not isinstance(observed_source_ids, frozenset):
        raise TypeError("observed_source_ids must be frozenset")
    if not isinstance(maximum_characters, int) or isinstance(maximum_characters, bool):
        raise TypeError("maximum_characters must be an integer")
    serialized = json.dumps(
        summary.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(serialized) > maximum_characters:
        raise ValueError("Working summary exceeds its character budget")
    for source_id in summary.referenced_source_ids():
        if source_id not in observed_source_ids:
            raise ValueError(f"Working summary cites unobserved source {source_id}")


def parse_agent_route_json(response_content: str) -> AgentRouteAction:
    envelope = agent_route_envelope_adapter.validate_json(response_content)
    return envelope.to_action()


def parse_search_query_json(response_content: str) -> SearchNotesAction:
    envelope = search_query_envelope_adapter.validate_json(response_content)
    return envelope.to_action()
