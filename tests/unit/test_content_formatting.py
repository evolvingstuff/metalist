from app.services.content_formatting import format_note_content_for_view


def test_format_note_content_for_view_no_matching_tag_keeps_delimiters() -> None:
    html = "<div>{{hello}}</div>"
    rendered = format_note_content_for_view(content_html=html, tags="")
    assert rendered == html


def test_format_note_content_for_view_scoped_monospace_consumes_delimiters() -> None:
    html = "<div>{{hello}}</div>"
    rendered = format_note_content_for_view(content_html=html, tags="{{@monospace}}")
    assert rendered == '<div><span class="meta-scope meta-monospace">hello</span></div>'


def test_format_note_content_for_view_scoped_multiple_meta_tags_apply_union() -> None:
    html = "<div>{{hello}}</div>"
    rendered = format_note_content_for_view(content_html=html, tags="{{@red @monospace}}")
    assert rendered == '<div><span class="meta-scope meta-monospace meta-red">hello</span></div>'


def test_format_note_content_for_view_depth_mismatch_does_not_match_subdepth() -> None:
    html = "<div>{{{hello}}}</div>"
    rendered = format_note_content_for_view(content_html=html, tags="{{@monospace}}")
    assert rendered == html


def test_format_note_content_for_view_nested_scopes() -> None:
    html = "<div>{{a [[b]]}}</div>"
    rendered = format_note_content_for_view(
        content_html=html,
        tags="{{@monospace}} [[@red]]",
    )
    assert (
        rendered
        == '<div><span class="meta-scope meta-monospace">a <span class="meta-scope meta-red">b</span></span></div>'
    )


def test_format_note_content_for_view_wrapper_spanning_tags() -> None:
    html = "<div>{{hello <b>world</b>}}</div>"
    rendered = format_note_content_for_view(content_html=html, tags="{{@red}}")
    assert rendered == '<div><span class="meta-scope meta-red">hello <b>world</b></span></div>'


def test_format_note_content_for_view_unclosed_wrapper_keeps_literal() -> None:
    html = "<div>{{hello</div>"
    rendered = format_note_content_for_view(content_html=html, tags="{{@red}}")
    assert rendered == html


def test_format_note_content_for_view_regular_scoped_tag_consumes_delimiters() -> None:
    html = "<div>[hello]</div>"
    rendered = format_note_content_for_view(content_html=html, tags="[foo]")
    assert rendered == "<div>hello</div>"


def test_format_note_content_for_view_global_applies_entire_note() -> None:
    html = "<div>hello</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@red")
    assert rendered == '<span class="meta-global meta-red"><div>hello</div></span>'
