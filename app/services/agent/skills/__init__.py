"""Load packaged agent skill resources."""

from __future__ import annotations

from importlib.resources import files


def load_skill(name: str) -> str:
    assert isinstance(name, str) and name != ""
    skill = files(__package__).joinpath(name).read_text(encoding="utf-8")
    assert skill.strip() != "", f"Agent skill resource is empty: {name}"
    return skill.rstrip("\n")


SEARCH_NOTES_SKILL = load_skill("search-notes.md")
SCOPED_INVESTIGATION_SKILL = load_skill("scoped-investigation.md")
SELECT_RELEVANT_EVIDENCE_SKILL = load_skill("select-relevant-evidence.md")
