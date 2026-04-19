from app.models.utils import note_data_to_html
from app.models.utils import render_note_data_read_only


def test_render_note_data_read_only_requires_tags_and_renders() -> None:
    tree = {
        "content": "<div>Hello</div>",
        "tags": "",
        "children": [
            {"content": "<div>Child</div>", "tags": "foo", "children": []},
        ],
    }
    rendered = render_note_data_read_only(tree)
    assert isinstance(rendered, dict)
    assert "content" in rendered
    assert "children" in rendered


def test_render_note_data_read_only_latex_is_ready_for_clipboard_html() -> None:
    tree = {
        "content": "<div>\\frac{1}{2}</div>",
        "tags": "@latex",
        "children": [],
    }

    rendered = render_note_data_read_only(tree)
    html = note_data_to_html(rendered)

    assert '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block">' in html
    assert "<mfrac>" in html
    assert "\\frac{1}{2}" not in html
