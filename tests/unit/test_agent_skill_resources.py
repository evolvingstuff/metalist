from __future__ import annotations

import importlib.resources
import importlib.util
from pathlib import Path

import pytest

import app.services.agent.skills as skill_resources


def test_skill_module_reads_resources_only_when_asked(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "staged-summary.md").write_text("Summary instructions", encoding="utf-8")
    monkeypatch.setattr(importlib.resources, "files", lambda package: tmp_path)
    specification = importlib.util.spec_from_file_location(
        "isolated_agent_skills",
        skill_resources.__file__,
        submodule_search_locations=[],
    )
    assert specification is not None and specification.loader is not None
    isolated_resources = importlib.util.module_from_spec(specification)

    # Importing needs no resource files; removed skills leave nothing behind.
    specification.loader.exec_module(isolated_resources)

    assert not hasattr(isolated_resources, "SCOPED_INVESTIGATION_SKILL")
    assert isolated_resources.load_skill("staged-summary.md") == "Summary instructions"
    with pytest.raises(FileNotFoundError):
        isolated_resources.load_skill("scoped-investigation.md")
