"""Expected agent-run failures caused by provider or model output."""

from __future__ import annotations


class AgentExecutionError(Exception):
    """Expected failure caused by provider/model output during an agent run."""
