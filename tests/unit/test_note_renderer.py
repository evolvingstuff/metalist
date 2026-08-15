from __future__ import annotations

from app.presentation.render.note_renderer import highlight_search_terms


def test_search_highlighting_ignores_or_operator() -> None:
    rendered = highlight_search_terms(
        "<div>alpha or beta</div>",
        "alpha OR beta",
    )

    assert rendered == (
        '<div><span class="search-highlight">alpha</span> or '
        '<span class="search-highlight">beta</span></div>'
    )


def test_search_highlighting_keeps_lowercase_or_as_a_term() -> None:
    rendered = highlight_search_terms("<div>this or that</div>", "or")

    assert rendered == '<div>this <span class="search-highlight">or</span> that</div>'
