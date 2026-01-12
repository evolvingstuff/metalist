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

