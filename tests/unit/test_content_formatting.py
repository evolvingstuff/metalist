from app.services.content_formatting import find_list_style
from app.services.content_formatting import format_note_content_for_view as _format_note_content_for_view


def format_note_content_for_view(*, content_html: str, tags: str) -> str:
    return _format_note_content_for_view(
        content_html=content_html,
        tags=tags,
        redact_passwords=False,
    )


def test_format_note_content_for_view_no_matching_tag_keeps_delimiters() -> None:
    html = "<div>{{hello}}</div>"
    rendered = format_note_content_for_view(content_html=html, tags="")
    assert rendered == html


def test_format_note_content_for_view_autolinks_plain_http_url() -> None:
    html = "<div>https://google.com</div>"
    rendered = format_note_content_for_view(content_html=html, tags="")
    assert (
        '<a href="https://google.com" target="_blank" rel="noopener noreferrer">https://google.com</a>'
        in rendered
    )


def test_format_note_content_for_view_autolinks_plain_http_url_without_trailing_punctuation() -> None:
    html = "<div>See https://google.com.</div>"
    rendered = format_note_content_for_view(content_html=html, tags="")
    assert (
        '<a href="https://google.com" target="_blank" rel="noopener noreferrer">https://google.com</a>.'
        in rendered
    )


def test_format_note_content_for_view_normalizes_existing_anchor_to_new_tab() -> None:
    html = '<div><a href="https://example.com">Example</a></div>'
    rendered = format_note_content_for_view(content_html=html, tags="")
    assert (
        '<a href="https://example.com" target="_blank" rel="noopener noreferrer">Example</a>'
        in rendered
    )


def test_format_note_content_for_view_leaves_hash_anchor_unchanged() -> None:
    html = '<div><a href="#note-123">Example</a></div>'
    rendered = format_note_content_for_view(content_html=html, tags="")
    assert '<a href="#note-123">Example</a>' in rendered
    assert 'target="_blank"' not in rendered


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


def test_format_note_content_for_view_basic_meta_tags_apply_classes() -> None:
    html = "<div>hello</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@bold @italic @heading @serif")
    assert 'meta-bold' in rendered
    assert 'meta-italic' in rendered
    assert 'meta-heading' in rendered
    assert 'meta-serif' in rendered


def test_format_note_content_for_view_dark_theme_meta_is_ignored() -> None:
    html = "<div>hello</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@dark-theme")
    assert rendered == html


def test_format_note_content_for_view_scoped_meta_tags_do_not_apply_globally() -> None:
    html = "<div>foo [bar]</div>"
    rendered = format_note_content_for_view(content_html=html, tags="[@red]")
    assert 'meta-global meta-red' not in rendered
    assert '<span class="meta-scope meta-red">bar</span>' in rendered


def test_format_note_content_for_view_scoped_strikethrough_uses_inline_box_wrapper() -> None:
    html = "<div>{hello}</div>"
    rendered = format_note_content_for_view(content_html=html, tags="{@strikethrough}")
    assert rendered == '<div><span class="meta-scope meta-box-inline meta-strikethrough">hello</span></div>'


def test_format_note_content_for_view_global_strikethrough_wraps_block_content() -> None:
    html = "<div>hello</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@strikethrough")
    assert rendered == '<div class="meta-global meta-box-block meta-strikethrough"><div>hello</div></div>'


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


def test_format_note_content_for_view_password_meta_redacts_underlying_value() -> None:
    html = "<div>sekret</div>"
    rendered = _format_note_content_for_view(
        content_html=html,
        tags="@password",
        redact_passwords=True,
    )
    assert 'data-copy-value="XXXXXX"' in rendered
    assert ">XXXXXX<" in rendered
    assert "sekret" not in rendered


def test_format_note_content_for_view_email_meta_renders_mailto_link() -> None:
    html = "<div>hello@example.com</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@email")
    assert 'meta-email' in rendered
    assert 'Email:' in rendered
    assert 'href="mailto:hello@example.com"' in rendered
    assert 'target="_blank"' in rendered
    assert 'rel="noopener noreferrer"' in rendered
    assert ">hello@example.com<" in rendered


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


def test_format_note_content_for_view_status_meta_strikethrough_wraps_inner_content() -> None:
    html = "<div>stuff</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@done @strikethrough")
    assert '<div class="meta-status-text"><div class="meta-status-format meta-box-block meta-strikethrough"><div>stuff</div></div></div>' in rendered


def test_format_note_content_for_view_markdown_meta_renders_plain_text_container() -> None:
    html = "<div># Title</div><div>Paragraph</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@markdown")
    assert 'class="meta-markdown"' in rendered
    assert "# Title" in rendered
    assert "Paragraph" in rendered
    assert "<div># Title</div>" not in rendered


def test_format_note_content_for_view_latex_meta_renders_plain_text_container() -> None:
    html = "<div>\\frac{1}{2}</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@latex")
    assert 'class="meta-latex"' in rendered
    assert "\\frac{1}{2}" in rendered
    assert "<div>\\frac{1}{2}</div>" not in rendered


def test_format_note_content_for_view_shell_meta_renders_script_block() -> None:
    html = "<div>echo hello</div><div>echo world</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@shell")
    assert 'class="meta-shell"' in rendered
    assert 'class="meta-shell-script"' in rendered
    assert "echo hello" in rendered
    assert "echo world" in rendered


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


def test_format_note_content_for_view_csv_meta_renders_table() -> None:
    html = "<div>a,b</div><div>1,2</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@csv")
    assert 'meta-csv' in rendered
    assert "<table" in rendered
    assert "<td>a</td>" in rendered
    assert "<td>b</td>" in rendered
    assert "<td>1</td>" in rendered
    assert "<td>2</td>" in rendered


def test_format_note_content_for_view_scoped_csv_meta_renders_table() -> None:
    html = "<div>((a,b,c</div><div>1,2,3))</div>"
    rendered = format_note_content_for_view(content_html=html, tags="((@csv))")
    assert 'meta-csv' in rendered
    assert 'meta-csv-inline' in rendered
    assert "<table" in rendered
    assert "<td>a</td>" in rendered
    assert "<td>b</td>" in rendered
    assert "<td>c</td>" in rendered
    assert "<td>1</td>" in rendered
    assert "<td>2</td>" in rendered
    assert "<td>3</td>" in rendered


def test_format_note_content_for_view_scoped_csv_meta_applies_scoped_formatting() -> None:
    html = "<div>((a,b,c</div><div>1,2,[3]))</div>"
    rendered = format_note_content_for_view(content_html=html, tags="((@csv)) [@red]")
    assert '<span class="meta-scope meta-red">3</span>' in rendered


def test_format_note_content_for_view_scoped_csv_meta_supports_nested_csv() -> None:
    html = "<div>((a,b,c</div><div>1,2,[x,y</div><div>3,4]</div><div>))</div>"
    rendered = format_note_content_for_view(content_html=html, tags="((@csv)) [@csv]")
    assert 'meta-csv-error' not in rendered
    assert rendered.count("<table") >= 2


def test_format_note_content_for_view_csv_meta_invalid_shows_error_badge() -> None:
    html = "<div>a,b</div><div>1,2,3</div>"
    rendered = format_note_content_for_view(content_html=html, tags="@csv")
    assert 'meta-csv-error' in rendered
    assert "Invalid CSV" in rendered
    assert "a,b" in rendered


def test_find_list_style_returns_none_without_list_tags() -> None:
    assert find_list_style("@red foo") is None


def test_find_list_style_prefers_last_tag() -> None:
    assert find_list_style("@list-bulleted @list-numbered") == "numbered"
    assert find_list_style("@list-numbered @list-bulleted") == "bulleted"


def test_find_list_style_ignores_wrapped_tags() -> None:
    assert find_list_style("((@list-bulleted))") is None
    assert find_list_style("[[@list-numbered]]") is None
