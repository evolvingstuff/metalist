"""Build the release-notes help skill from the README "Changes in x.y.z" sections.

The skill file ``skills/help-releases.md`` is generated, not edited by hand:
``scripts/sync_release_notes_help.py`` rewrites it from README.md, and a unit
test fails when the two drift apart.
"""

from __future__ import annotations

import re


_CHANGES_HEADING_RE = re.compile(r"^## Changes in (\d+\.\d+\.\d+)$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
RELEASE_NOTES_SKILL_HEADER = (
    "# MetaList release notes\n"
    "\n"
    "What changed in each MetaList version, newest first, from the packaged\n"
    "README. Changes made after the newest listed version are not described here.\n"
    "Compare with installed_version from the help lookup to tell the user whether\n"
    "they already have a release. Version info offers updates (see the data topic)."
)


def release_notes_skill_from_readme(readme_text: str) -> str:
    """Return the skill text: one ``## x.y.z`` section per README changes section."""
    if not isinstance(readme_text, str):
        raise TypeError("README text must be a string")
    sections: list[tuple[str, list[str]]] = []
    for line in readme_text.splitlines():
        heading = _CHANGES_HEADING_RE.match(line)
        if heading is not None:
            sections.append((heading.group(1), []))
        elif line.startswith("## "):
            if sections:
                break
        elif sections:
            sections[-1][1].append(_MARKDOWN_LINK_RE.sub(r"\1", line))
    if not sections:
        raise ValueError('README has no "## Changes in x.y.z" sections')
    versions = [version for version, _lines in sections]
    if len(set(versions)) != len(versions):
        raise ValueError("README lists a release more than once")
    parts = [RELEASE_NOTES_SKILL_HEADER]
    for version, lines in sections:
        body = "\n".join(lines).strip()
        if body == "":
            raise ValueError(f"README changes section for {version} is empty")
        parts.append(f"## {version}\n\n{body}")
    return "\n\n".join(parts)
