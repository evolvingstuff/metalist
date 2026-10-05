"""Regenerate the release-notes help skill from README.md.

Run after editing a README "Changes in x.y.z" section:

    .venv/bin/python scripts/sync_release_notes_help.py
"""

from __future__ import annotations

from pathlib import Path

from app.services.agent.release_notes import release_notes_skill_from_readme


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPOSITORY_ROOT / "README.md"
SKILL_PATH = REPOSITORY_ROOT / "app" / "services" / "agent" / "skills" / "help-releases.md"


def main() -> None:
    skill_text = release_notes_skill_from_readme(README_PATH.read_text(encoding="utf-8"))
    SKILL_PATH.write_text(skill_text + "\n", encoding="utf-8")
    print(f"Wrote {SKILL_PATH.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
