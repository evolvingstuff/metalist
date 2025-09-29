from copy import deepcopy

from app.models.utils import render_note_data_read_only


def test_render_note_data_read_only_strips_comment_markers():
    original = {
        "content": "<div>hello /* comment */ world</div>",
        "children": [
            {"content": "child /* nested */ text", "children": []}
        ],
        "created_at": None,
        "children_extra": "ignored"
    }

    source = deepcopy(original)
    rendered = render_note_data_read_only(source)

    assert "/*" not in rendered["content"]
    assert "/*" not in rendered["children"][0]["content"]
    assert rendered.get("children_extra") == "ignored"

    # Source dict should remain unchanged
    assert "/* comment */" in source["content"]
    assert "/* nested */" in source["children"][0]["content"]
