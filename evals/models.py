"""Required, versioned inputs for isolated prompt regression cases."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(StrictModel):
    role: Literal["system", "developer", "user", "assistant"]
    content: str


class PreviousOutput(StrictModel):
    role: Literal["assistant"]
    from_step: int = Field(ge=0)


class PromptBinding(StrictModel):
    target: Literal["message", "json_instruction", "skill"]
    message_index: int = Field(ge=0)
    file: str = Field(min_length=1)
    variables: dict[str, str]


class Criterion(StrictModel):
    id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)


class ActionExpectation(StrictModel):
    kind: Literal["action"]
    # Dictionaries match specified fields; arrays match exactly, including order.
    alternatives: list[dict] = Field(min_length=1)


class OutputExpectation(StrictModel):
    kind: Literal["output"]
    criteria: list[Criterion] = Field(min_length=1)
    reference_facts: str

    @model_validator(mode="after")
    def unique_criteria(self):
        ids = [criterion.id for criterion in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("Criterion IDs must be unique")
        return self


class Step(StrictModel):
    kind: Literal["structured", "text"]
    messages: list[Message | PreviousOutput] = Field(min_length=1)
    response_model: str
    response_schema: dict
    max_output_tokens: int = Field(ge=0)
    current_user_request: str = Field(min_length=1)
    prompt_bindings: list[PromptBinding]
    expectation: ActionExpectation | OutputExpectation

    @model_validator(mode="after")
    def validate_contract(self):
        if self.kind == "text" and (self.response_model or self.max_output_tokens < 1):
            raise ValueError("Text steps require a positive output limit and no response model")
        if self.kind == "structured" and (not self.response_model or self.max_output_tokens != 0):
            raise ValueError("Structured steps use the production schema's output limit")
        if self.expectation.kind == "action" and self.kind != "structured":
            raise ValueError("Action expectations require a structured step")
        if self.expectation.kind == "action" and any(not item for item in self.expectation.alternatives):
            raise ValueError("Action alternatives must assert at least one field")
        indices = [binding.message_index for binding in self.prompt_bindings]
        if len(set(indices)) != len(indices):
            raise ValueError("Each message can have only one prompt binding")
        for index in indices:
            if index >= len(self.messages) or not isinstance(self.messages[index], Message):
                raise ValueError("Prompt binding must select a literal message")
            binding = next(binding for binding in self.prompt_bindings if binding.message_index == index)
            if binding.target in {"message", "skill"} and self.messages[index].role not in {"system", "developer"}:
                raise ValueError("Whole-message bindings must target instruction messages")
            if binding.target == "json_instruction" and not self.messages[index].content.startswith(("FINAL_RESPONSE_REQUEST\n", "METALIST_HELP_REQUEST\n")):
                raise ValueError("JSON instruction bindings must target FINAL_RESPONSE_REQUEST or METALIST_HELP_REQUEST")
        return self


class RegressionCase(StrictModel):
    schema_version: Literal[1]
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    reviewed: bool
    model: str = Field(min_length=1)
    thinking_level: Literal["off", "low", "medium", "high"]
    steps: list[Step] = Field(min_length=1)
    provenance: dict

    @model_validator(mode="after")
    def validate_previous_steps(self):
        for index, step in enumerate(self.steps):
            for message in step.messages:
                if isinstance(message, PreviousOutput) and message.from_step >= index:
                    raise ValueError("Previous output must refer to an earlier step")
        return self


class JudgeConfig(StrictModel):
    model: str = Field(min_length=1)
    thinking_level: Literal["off", "low", "medium", "high"]
    prompt: str = Field(min_length=1)
