from __future__ import annotations

import pytest

from app.services.agent.web_settings import AgentWebSettings
from app.services.agent.web_settings import DEFAULT_AGENT_WEB_SETTINGS
from app.services.agent.web_settings import WEB_ACCESS_MODE_PREFERENCE_KEY
from app.services.agent.web_settings import resolve_agent_web_settings
from app.services.agent.web_settings import validate_web_access_mode


def test_web_access_defaults_to_none() -> None:
    assert resolve_agent_web_settings(preferences={}) == DEFAULT_AGENT_WEB_SETTINGS
    assert DEFAULT_AGENT_WEB_SETTINGS == AgentWebSettings(mode="none")
    assert not DEFAULT_AGENT_WEB_SETTINGS.can_open_pages


@pytest.mark.parametrize(
    ("mode", "can_open_pages"),
    [
        ("none", False),
        ("contextual", True),
        ("full", True),
    ],
)
def test_web_access_modes_define_capabilities(
    mode: str,
    can_open_pages: bool,
) -> None:
    settings = resolve_agent_web_settings(
        preferences={WEB_ACCESS_MODE_PREFERENCE_KEY: mode}
    )
    assert settings.can_open_pages is can_open_pages


@pytest.mark.parametrize("value", ["", "off", "context", "FULL", " full "])
def test_web_access_mode_rejects_unknown_values(value: str) -> None:
    with pytest.raises(ValueError, match="Unsupported agent web access mode"):
        validate_web_access_mode(value)


def test_web_access_mode_rejects_non_text() -> None:
    with pytest.raises(TypeError, match="must be text"):
        validate_web_access_mode(1)  # type: ignore[arg-type]
