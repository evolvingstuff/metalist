"""Agent-stage regression cases: a whole tool-using agent run against fixed fixtures.

A case fixes the conversation, the notes in the view, the selected note, the web
mode and the pages a fixture web serves, and how the user answers any question.
It expects tool calls (and forbids others), whether a confirmation is asked, and
judges the final answer. Production instructions, skills and tool schemas are never
stored in a case: every run uses the current production agent loop.
"""

from typing import Literal

from pydantic import Field, model_validator

from evals.models import Criterion, ConversationMessage, SelectedNoteFixture, SelectedTreeFixture
from evals.models import StrictModel, UnavailableSelectionFixture


ToolName = Literal[
    "lookup_metalist_help", "view_overview", "search_view_notes", "read_view_notes", "open_web_pages",
    "open_menu", "propose_tag_generation", "propose_tag_review", "summarize_view",
]
# Default order (agent.md): help and menus, then notes, then the web, then changes.
TOOL_ORDER_RANK: dict[str, int] = {
    "lookup_metalist_help": 1, "open_menu": 1,
    "view_overview": 2, "search_view_notes": 2, "read_view_notes": 2,
    "open_web_pages": 3,
    "propose_tag_generation": 4, "propose_tag_review": 4, "summarize_view": 4,
}


class ViewNoteFixture(StrictModel):
    note_id: str = Field(min_length=1)
    parent_id: str
    content_text: str
    tags: str
    # Pending tag proposals, space-separated like the tag bar.
    proposed_tags: str


class ViewFixture(StrictModel):
    scope_kind: Literal["search", "all_notes", "untagged"]
    label: str = Field(min_length=1)
    search_query: str
    sort_mode: str = Field(min_length=1)
    notes: list[ViewNoteFixture]

    @model_validator(mode="after")
    def validate_tree(self):
        ids = [note.note_id for note in self.notes]
        if len(set(ids)) != len(ids):
            raise ValueError("View note ids must be unique")
        known = set()
        for note in self.notes:
            if note.parent_id and note.parent_id not in known:
                raise ValueError("A view note's parent must be listed before it")
            known.add(note.note_id)
        return self


class WebLinkFixture(StrictModel):
    # Fixed citation id the judge criteria refer to; live runs are mapped onto it.
    evidence_id: str = Field(min_length=1)
    title: str
    url: str = Field(min_length=1)


class WebPageFixture(StrictModel):
    evidence_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str
    content_text: str = Field(min_length=1)
    links: list[WebLinkFixture]


class WebFixture(StrictModel):
    mode: Literal["none", "contextual", "full"]
    # Pages the fixture web serves when the agent opens their address.
    pages: list[WebPageFixture]
    # Addresses of served pages already opened earlier in the chat.
    retained_urls: list[str]

    @model_validator(mode="after")
    def retained_pages_are_served(self):
        served = {page.url for page in self.pages}
        if not set(self.retained_urls) <= served:
            raise ValueError("Retained addresses must be among the served pages")
        return self


class RequiredCall(StrictModel):
    """At least one call to one of `tools` whose arguments contain one of `arguments_any_of`."""

    tools: list[ToolName] = Field(min_length=1)
    # Empty: any arguments. Lists in an expected dict must be a subset of the actual list.
    arguments_any_of: list[dict]


class AgentExpectation(StrictModel):
    required_calls: list[RequiredCall]
    forbidden_tools: list[ToolName]
    # Specific calls that must not happen (same matching as required calls).
    forbidden_calls: list[RequiredCall]
    confirmation: Literal["asked", "not_asked", "any"]
    # Empty criteria: the answer is not judged.
    answer_criteria: list[Criterion]
    reference_facts: str

    @model_validator(mode="after")
    def unique_criteria(self):
        ids = [criterion.id for criterion in self.answer_criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("Criterion IDs must be unique")
        required = {tool for call in self.required_calls for tool in call.tools}
        if required & set(self.forbidden_tools):
            raise ValueError("A tool cannot be both required and forbidden")
        return self


class AgentCase(StrictModel):
    schema_version: Literal[3]
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    reviewed: bool
    # Live evals run on Luna at Low thinking only.
    model: Literal["gpt-5.6-luna"]
    thinking_level: Literal["low"]
    conversation: list[ConversationMessage] = Field(min_length=1)
    view: ViewFixture
    selected_note: SelectedNoteFixture | SelectedTreeFixture | UnavailableSelectionFixture
    web: WebFixture
    # How the simulated user answers any Yes/No or scope question.
    answer_questions: Literal["yes", "no"]
    expectation: AgentExpectation
    provenance: dict

    @model_validator(mode="after")
    def ends_with_the_request(self):
        if self.conversation[-1].role != "user":
            raise ValueError("Conversation must end with the current user request")
        return self
