"""Explicit model routing policy for agent inference stages."""

from __future__ import annotations

from enum import Enum


class InferencePurpose(str, Enum):
    ACTION_SELECTION = "action-selection"
    FINAL_RESPONSE = "final-response"


class SingleModelPolicy:
    """Route every current stage to the model selected in the chat UI."""

    def for_stage(self, *, purpose: InferencePurpose, selected_model: str) -> str:
        if not isinstance(purpose, InferencePurpose):
            raise TypeError("purpose must be an InferencePurpose")
        if not isinstance(selected_model, str) or selected_model.strip() == "":
            raise ValueError("selected_model must be a non-empty string")
        return selected_model.strip()
