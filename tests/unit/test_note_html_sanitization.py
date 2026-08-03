from __future__ import annotations

import pytest

from app.security.note_html import sanitize_note_html


@pytest.mark.parametrize(
    ("malicious_html", "forbidden_fragments"),
    [
        ("<script>alert(1)</script><div>kept</div>", ("script", "alert(1)")),
        ("<img src=x onerror=alert(1)>", ("onerror",)),
        ('<a href="javascript:alert(1)">click</a>', ("javascript:", "href=")),
        ('<svg><a href="javascript:alert(1)">x</a></svg>', ("svg", "javascript:")),
        ('<div style="background-image:url(https://attacker.test/x); margin-left: 12px">x</div>', ("background-image", "attacker.test")),
        ('<img src="data:text/html;base64,PHNjcmlwdD4=">', ("data:text/html",)),
        ('<form><input autofocus onfocus=alert(1)></form>', ("form", "input", "onfocus")),
    ],
)
def test_sanitize_note_html_removes_executable_markup(
    malicious_html: str,
    forbidden_fragments: tuple[str, ...],
) -> None:
    sanitized = sanitize_note_html(malicious_html)

    for fragment in forbidden_fragments:
        assert fragment not in sanitized.casefold()


def test_sanitize_note_html_preserves_supported_note_formatting() -> None:
    content = (
        '<h2><strong>Heading</strong></h2>'
        '<div style="margin-left: 24px; text-indent: 0px">Indented</div>'
        '<ol start="3"><li>Three</li></ol>'
        '<table><tbody><tr><td colspan="2">Cell</td></tr></tbody></table>'
        '<a href="https://example.com/path?q=1" title="Example">Link</a>'
        '<img src="data:image/png;base64,AAAA" alt="Example" style="max-width: 100%; height: auto">'
    )

    sanitized = sanitize_note_html(content)

    assert "<h2><strong>Heading</strong></h2>" in sanitized
    assert 'style="margin-left:24px;text-indent:0px"' in sanitized
    assert '<ol start="3"><li>Three</li></ol>' in sanitized
    assert '<td colspan="2">Cell</td>' in sanitized
    assert 'href="https://example.com/path?q=1"' in sanitized
    assert 'src="data:image/png;base64,AAAA"' in sanitized
    assert 'style="max-width:100%;height:auto"' in sanitized


def test_sanitize_note_html_is_idempotent() -> None:
    content = '<div style="margin-left: 12px"><a href="https://example.com">safe</a></div>'
    once = sanitize_note_html(content)

    assert sanitize_note_html(once) == once


def test_sanitize_note_html_rejects_malformed_layout_attributes() -> None:
    content = '<img src="https://example.com/x.png" width="100%"><td colspan="-4">x</td>'

    sanitized = sanitize_note_html(content)

    assert "width=" not in sanitized
    assert "colspan=" not in sanitized


def test_sanitize_note_html_rejects_non_string_input() -> None:
    with pytest.raises(TypeError, match="content must be a string"):
        sanitize_note_html(None)  # type: ignore[arg-type]
