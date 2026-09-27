"""Validate Markdown boundaries that must survive model-generated help text."""

import re


_FENCE_LINE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def validate_balanced_markdown_fences(markdown: str) -> str:
    """Reject a fenced code block that remains open at the end of Markdown."""
    assert isinstance(markdown, str)
    open_character = ""
    open_length = 0
    for line in markdown.splitlines():
        match = _FENCE_LINE.match(line)
        if match is None:
            continue
        fence, remainder = match.groups()
        fence_character = fence[0]
        if open_character == "":
            if fence_character == "`" and "`" in remainder:
                continue
            open_character = fence_character
            open_length = len(fence)
            continue
        if (
            fence_character == open_character
            and len(fence) >= open_length
            and remainder.strip() == ""
        ):
            open_character = ""
            open_length = 0
    if open_character != "":
        raise ValueError("Help answer contains an unclosed Markdown code fence")
    return markdown
