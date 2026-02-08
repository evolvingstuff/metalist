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


def test_format_note_content_for_view_username_meta_renders_credential_row() -> None:
    html = "<div><b>tomlahore1</b></div>"
    rendered = format_note_content_for_view(content_html=html, tags="@username")
    assert 'meta-credential-username' in rendered
    assert 'Username:' in rendered
    assert 'data-copy-value="tomlahore1"' in rendered
    assert ">tomlahore1<" in rendered


def test_format_note_content_for_view_password_meta_renders_copyable_value() -> None:
    html = "<div>sekret</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@password")
    assert 'meta-credential-password' in rendered
    assert 'Password:' in rendered
    assert 'data-copy-value="sekret"' in rendered
    assert ">sekret<" in rendered


def test_format_note_content_for_view_password_meta_applies_other_global_classes() -> None:
    html = "<div>sekret</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@password @red")
    assert 'meta-credential-value meta-red' in rendered


def test_format_note_content_for_view_todo_meta_renders_status_row() -> None:
    html = "<div>stuff to do</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@todo")
    assert 'meta-status-todo' in rendered
    assert 'meta-status-toggle' in rendered
    assert '<div class="meta-status-text">' in rendered
    assert html in rendered


def test_format_note_content_for_view_done_meta_renders_status_row() -> None:
    html = "<div>stuff done</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@done")
    assert 'meta-status-done' in rendered
    assert 'meta-status-toggle' in rendered
    assert '<div class="meta-status-text">' in rendered
    assert html in rendered


def test_format_note_content_for_view_status_meta_applies_other_global_classes() -> None:
    html = "<div>stuff</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@done @red")
    assert 'meta-status-text meta-red' in rendered


def test_format_note_content_for_view_json_meta_formats_and_highlights() -> None:
    html = '<div>{"name": "MetaList", "count": 2}</div>'
    rendered = format_note_content_for_view(content_html=html, tags="@json")
    assert 'meta-json' in rendered
    assert '<span class="json-key">"name"</span>' in rendered
    assert '<span class="json-string">"MetaList"</span>' in rendered
    assert '<span class="json-number">2</span>' in rendered


def test_format_note_content_for_view_json_meta_invalid_shows_error_badge() -> None:
    html = "<div>{invalid}</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@json")
    assert 'meta-json-error' in rendered
    assert "Invalid JSON" in rendered
    assert "{invalid}" in rendered
