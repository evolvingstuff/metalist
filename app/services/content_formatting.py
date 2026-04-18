from __future__ import annotations

import base64
import csv
import html
import io
import json
import re
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Mapping, Set, Tuple

from app.utils.text_utils import strip_html
from app.services.ontology_rules_store import get_ontology_if_ready


_OPEN_TO_CLOSE = {
    "[": "]",
    "{": "}",
    "(": ")",
}
_CLOSE_TO_OPEN = {value: key for key, value in _OPEN_TO_CLOSE.items()}

_MAX_DELIMITER_DEPTH = 3

_META_TAG_TO_CLASS = {
    "monospace": "meta-monospace",
    "heading": "meta-heading",
    "red": "meta-red",
    "green": "meta-green",
    "blue": "meta-blue",
    "grey": "meta-grey",
    "bold": "meta-bold",
    "italic": "meta-italic",
    "strikethrough": "meta-strikethrough",
    "serif": "meta-serif",
    "copyable": "meta-copyable",
}

_LIST_STYLE_TAGS = {
    "list-bulleted": "bulleted",
    "list-numbered": "numbered",
}

_RENDERER_TAGS = frozenset({"markdown", "latex", "json", "csv", "shell"})

_CREDENTIAL_TAGS = frozenset({"username", "password"})
_EMAIL_TAGS = frozenset({"email"})

_CREDENTIAL_META = {
    "username": {
        "label": "Username",
        "icon": (
            '<svg class="meta-credential-icon-svg" viewBox="0 0 24 24" '
            'aria-hidden="true" focusable="false">'
            '<path fill="currentColor" d="M12 12c2.761 0 5-2.239 5-5'
            's-2.239-5-5-5-5 2.239-5 5 2.239 5 5 5Zm0 2c-3.866 0-7'
            ' 2.239-7 5v3h14v-3c0-2.761-3.134-5-7-5Z"/>'
            "</svg>"
        ),
    },
    "password": {
        "label": "Password",
        "icon": (
            '<svg class="meta-credential-icon-svg" viewBox="0 0 24 24" '
            'aria-hidden="true" focusable="false">'
            '<path fill="currentColor" d="M7 10V7a5 5 0 0110 0v3h1a2'
            ' 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2v-8a2 2 0 012-2'
            'h1zm2 0h6V7a3 3 0 00-6 0v3z"/>'
            "</svg>"
        ),
    },
}

_EMAIL_META = {
    "email": {
        "label": "Email",
        "icon": (
            '<svg class="meta-email-icon-svg" viewBox="0 0 24 24" '
            'aria-hidden="true" focusable="false">'
            '<path fill="currentColor" d="M4 4h16a2 2 0 012 2v12a2 2 '
            '0 01-2 2H4a2 2 0 01-2-2V6a2 2 0 012-2zm0 4.236V18h16V8.236'
            'l-7.4 5.18a1 1 0 01-1.2 0L4 8.236zm0-2.472l8 5.6 8-5.6V6H4v-.236z"/>'
            "</svg>"
        ),
    },
}

_STATUS_TAGS = frozenset({"todo", "done"})

_STATUS_META = {
    "todo": {
        "icon": (
            '<svg class="meta-status-icon-svg" viewBox="0 0 24 24" '
            'aria-hidden="true" focusable="false">'
            '<rect x="3" y="3" width="18" height="18" rx="3" ry="3" '
            'fill="none" stroke="currentColor" stroke-width="2" />'
            "</svg>"
        ),
    },
    "done": {
        "icon": (
            '<svg class="meta-status-icon-svg" viewBox="0 0 24 24" '
            'aria-hidden="true" focusable="false">'
            '<rect x="3" y="3" width="18" height="18" rx="3" ry="3" '
            'fill="none" stroke="currentColor" stroke-width="2" />'
            '<path d="M7 12l3 3 7-7" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />'
            "</svg>"
        ),
    },
}

_JSON_NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_LATEX_PLACEHOLDER_PREFIX = "@@MLLATEX["
_LATEX_PLACEHOLDER_SUFFIX = "]@@"
_PLAIN_URL_RE = re.compile(r"https?://[^\s<]+", re.IGNORECASE)
_HTML_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")
_ANCHOR_START_TAG_RE = re.compile(r"<\s*a\b", re.IGNORECASE)
_ANCHOR_END_TAG_RE = re.compile(r"<\s*/\s*a\s*>", re.IGNORECASE)
_ANCHOR_HREF_ATTR_RE = re.compile(r'(\bhref\s*=\s*)(["\'])(.*?)\2', re.IGNORECASE)
_ANCHOR_TARGET_ATTR_RE = re.compile(r'(\btarget\s*=\s*)(["\'])(.*?)\2', re.IGNORECASE)
_ANCHOR_REL_ATTR_RE = re.compile(r'(\brel\s*=\s*)(["\'])(.*?)\2', re.IGNORECASE)
_NEW_TAB_REL_TOKENS = ("noopener", "noreferrer")
_BLOCK_HTML_TAG_RE = re.compile(
    r"<(?:blockquote|div|dl|fieldset|figure|figcaption|footer|form|h[1-6]|header|hr|li|ol|p|pre|section|table|tbody|td|tfoot|th|thead|tr|ul)\b",
    re.IGNORECASE,
)


def list_known_meta_tag_terms() -> FrozenSet[str]:
    terms = {f"@{name}" for name in _META_TAG_TO_CLASS.keys()}
    terms.update(f"@{name}" for name in _LIST_STYLE_TAGS.keys())
    terms.update(f"@{name}" for name in _CREDENTIAL_TAGS)
    terms.update(f"@{name}" for name in _EMAIL_TAGS)
    terms.update(f"@{name}" for name in _STATUS_TAGS)
    terms.add("@markdown")
    terms.add("@LaTeX")
    terms.add("@shell")
    terms.add("@json")
    terms.add("@csv")
    return frozenset(terms)


def find_global_credential_tag(tags: str) -> str | None:
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")
    return _find_global_credential_tag(tags)

@dataclass(frozen=True, slots=True)
class MetaTagConfig:
    global_tags: FrozenSet[str]
    wrappers_to_consume: FrozenSet[Tuple[str, int]]
    scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]]
    scoped_renderers: Mapping[Tuple[str, int], str]


def format_note_content_for_view(*, content_html: str, tags: str, redact_passwords: bool) -> str:
    if not isinstance(content_html, str):
        raise TypeError(f"content_html must be a string, got {type(content_html)}")
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")
    if not isinstance(redact_passwords, bool):
        raise TypeError(f"redact_passwords must be a bool, got {type(redact_passwords)}")

    config = _parse_meta_tags(tags)
    implied_meta = _infer_implied_meta_tags(tags)
    if implied_meta:
        config = MetaTagConfig(
            global_tags=frozenset(set(config.global_tags) | set(implied_meta)),
            wrappers_to_consume=config.wrappers_to_consume,
            scoped_tags=config.scoped_tags,
            scoped_renderers=config.scoped_renderers,
        )
    credential_tag = _find_global_credential_tag(tags)
    email_tag = _find_global_email_tag(tags)
    status_tag = _find_global_status_tag(tags)
    renderer_tag = _find_first_renderer_tag(tags)

    if (
        renderer_tag is None
        and not config.global_tags
        and not config.wrappers_to_consume
        and credential_tag is None
        and email_tag is None
        and status_tag is None
    ):
        return _linkify_view_links(content_html)

    output = content_html
    apply_wrappers = True
    if renderer_tag == "csv":
        apply_wrappers = False
    if apply_wrappers and config.wrappers_to_consume:
        output = _apply_scoped_meta_tags(
            content_html=output,
            wrappers_to_consume=config.wrappers_to_consume,
            scoped_tags=config.scoped_tags,
            scoped_renderers=config.scoped_renderers,
        )

    if renderer_tag is not None:
        if renderer_tag == "shell":
            return _render_shell_meta(
                content_html=output,
                formatting_tags=config.global_tags,
            )
        if renderer_tag == "markdown":
            return _render_markdown_meta(
                content_html=output,
                formatting_tags=config.global_tags,
            )
        if renderer_tag == "latex":
            return _render_latex_meta(
                content_html=output,
                formatting_tags=config.global_tags,
            )
        if renderer_tag == "json":
            return _render_json_meta(
                content_html=output,
                formatting_tags=config.global_tags,
            )
        if renderer_tag == "csv":
            return _render_csv_meta(
                content_html=output,
                formatting_tags=config.global_tags,
                inline=False,
                cell_wrappers=frozenset(),
                cell_scoped_tags={},
                cell_scoped_renderers={},
            )
        raise KeyError(f"Unknown renderer tag: {renderer_tag}")

    if credential_tag is not None:
        return _linkify_view_links(
            _render_credential_meta(
                content_html=output,
                credential_tag=credential_tag,
                formatting_tags=config.global_tags,
                redact_passwords=redact_passwords,
            )
        )

    if email_tag is not None:
        return _linkify_view_links(
            _render_email_meta(
                content_html=output,
                email_tag=email_tag,
                formatting_tags=config.global_tags,
            )
        )

    if status_tag is not None:
        return _linkify_view_links(
            _render_status_meta(
                content_html=output,
                status_tag=status_tag,
                formatting_tags=config.global_tags,
            )
        )

    if config.global_tags:
        copy_attr = ""
        if "copyable" in config.global_tags:
            plain_text = _extract_plain_text(output)
            copy_attr = _copyable_attr(config.global_tags, plain_text)
        output = _wrap_meta_html(
            inner_html=output,
            tag_names=config.global_tags,
            wrapper_class="meta-global",
            copy_attr=copy_attr,
            allow_block_wrapper=True,
        )

    return _linkify_view_links(output)


def _linkify_view_links(content_html: str) -> str:
    if not isinstance(content_html, str):
        raise TypeError(f"content_html must be a string, got {type(content_html)}")
    if content_html == "":
        return ""

    pieces = _HTML_TAG_SPLIT_RE.split(content_html)
    output: List[str] = []
    inside_anchor_depth = 0

    for piece in pieces:
        if piece == "":
            continue
        if piece.startswith("<") and piece.endswith(">"):
            normalized_tag = _normalize_anchor_tag(piece)
            output.append(normalized_tag)
            if _ANCHOR_END_TAG_RE.fullmatch(piece):
                if inside_anchor_depth > 0:
                    inside_anchor_depth -= 1
                continue
            if _ANCHOR_START_TAG_RE.match(piece):
                inside_anchor_depth += 1
            continue
        if inside_anchor_depth > 0:
            output.append(piece)
            continue
        output.append(_autolink_plain_urls_in_text(piece))

    return "".join(output)


def _autolink_plain_urls_in_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError(f"text must be a string, got {type(text)}")
    if text == "":
        return ""

    output: List[str] = []
    cursor = 0
    for match in _PLAIN_URL_RE.finditer(text):
        raw_url = match.group(0)
        link_text, trailing_suffix = _split_trailing_url_punctuation(raw_url)
        if link_text == "":
            continue
        output.append(text[cursor:match.start()])
        href_value = html.escape(html.unescape(link_text), quote=True)
        output.append(
            f'<a href="{href_value}" target="_blank" rel="noopener noreferrer">{link_text}</a>'
        )
        output.append(trailing_suffix)
        cursor = match.end()
    output.append(text[cursor:])
    return "".join(output)


def _split_trailing_url_punctuation(raw_url: str) -> Tuple[str, str]:
    if not isinstance(raw_url, str):
        raise TypeError(f"raw_url must be a string, got {type(raw_url)}")
    if raw_url == "":
        return "", ""

    url_text = raw_url
    suffix = ""
    while url_text:
        last_char = url_text[-1]
        if last_char in {".", ",", "!", "?", ";", ":", "'", '"'}:
            suffix = last_char + suffix
            url_text = url_text[:-1]
            continue
        if last_char == ")":
            if url_text.count(")") > url_text.count("("):
                suffix = ")" + suffix
                url_text = url_text[:-1]
                continue
            break
        if last_char == "]":
            if url_text.count("]") > url_text.count("["):
                suffix = "]" + suffix
                url_text = url_text[:-1]
                continue
            break
        if last_char == "}":
            if url_text.count("}") > url_text.count("{"):
                suffix = "}" + suffix
                url_text = url_text[:-1]
                continue
            break
        break

    return url_text, suffix


def _normalize_anchor_tag(tag_html: str) -> str:
    if not isinstance(tag_html, str):
        raise TypeError(f"tag_html must be a string, got {type(tag_html)}")
    if not _ANCHOR_START_TAG_RE.match(tag_html):
        return tag_html

    href_match = _ANCHOR_HREF_ATTR_RE.search(tag_html)
    if href_match is None:
        return tag_html
    href_value = href_match.group(3)
    if href_value.startswith("#"):
        return tag_html

    normalized = _ensure_anchor_target_attr(tag_html)
    normalized = _ensure_anchor_rel_attr(normalized)
    return normalized


def _ensure_anchor_target_attr(tag_html: str) -> str:
    if _ANCHOR_TARGET_ATTR_RE.search(tag_html):
        return _ANCHOR_TARGET_ATTR_RE.sub(r'\1\2_blank\2', tag_html, count=1)
    if tag_html.endswith("/>"):
        return f'{tag_html[:-2]} target="_blank"/>'
    return f'{tag_html[:-1]} target="_blank">'


def _ensure_anchor_rel_attr(tag_html: str) -> str:
    rel_match = _ANCHOR_REL_ATTR_RE.search(tag_html)
    if rel_match is not None:
        existing_tokens = rel_match.group(3).split()
        merged_tokens = list(existing_tokens)
        for token in _NEW_TAB_REL_TOKENS:
            if token not in merged_tokens:
                merged_tokens.append(token)
        merged_value = " ".join(merged_tokens)
        return _ANCHOR_REL_ATTR_RE.sub(
            rf'\1\2{merged_value}\2',
            tag_html,
            count=1,
        )
    if tag_html.endswith("/>"):
        return f'{tag_html[:-2]} rel="noopener noreferrer"/>'
    return f'{tag_html[:-1]} rel="noopener noreferrer">'


def find_list_style(tags: str) -> str | None:
    if not isinstance(tags, str):
        raise TypeError("tags must be a string")

    list_style = None
    tokens = _tokenize_tag_bar(tags)
    for token in tokens:
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is not None:
            continue
        if base.startswith("@"):
            tag_name = base[1:].casefold()
            if tag_name in _LIST_STYLE_TAGS:
                list_style = _LIST_STYLE_TAGS[tag_name]
    return list_style


def _infer_implied_meta_tags(tags: str) -> FrozenSet[str]:
    if not isinstance(tags, str):
        raise TypeError("tags must be a string")

    base_terms = frozenset(
        term for term in _extract_tag_terms(tags) if not term.startswith("@")
    )
    if not base_terms:
        return frozenset()

    ontology = get_ontology_if_ready()
    if ontology is None or ontology.is_empty:
        return frozenset()

    implied = ontology.infer_implication_only(base_tags=base_terms)
    meta: Set[str] = set()
    for term in implied:
        if not term.startswith("@"):
            continue
        tag_name = term[1:]
        if tag_name in _META_TAG_TO_CLASS:
            meta.add(tag_name)
    return frozenset(meta)


def _extract_tag_terms(tags: str) -> FrozenSet[str]:
    terms: Set[str] = set()
    for token in _tokenize_tag_bar(tags):
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is None:
            terms.add(base)
            continue
        for inner in base.split():
            if inner:
                terms.add(inner)
    return frozenset(terms)


def _find_first_renderer_tag(tags: str) -> str | None:
    tokens = _tokenize_tag_bar(tags)
    for token in tokens:
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is not None:
            continue
        if not base.startswith("@"):
            continue
        tag_name = base[1:].casefold()
        if tag_name in _RENDERER_TAGS:
            return tag_name
    return None


def _find_global_credential_tag(tags: str) -> str | None:
    tokens = _tokenize_tag_bar(tags)
    found_password = False
    found_username = False
    for token in tokens:
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is not None:
            continue
        if not base.startswith("@"):
            continue
        tag_name = base[1:].casefold()
        if tag_name == "password":
            found_password = True
            continue
        if tag_name == "username":
            found_username = True
            continue

    if found_password:
        return "password"
    if found_username:
        return "username"
    return None


def _find_global_email_tag(tags: str) -> str | None:
    tokens = _tokenize_tag_bar(tags)
    for token in tokens:
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is not None:
            continue
        if base.casefold() == "@email":
            return "email"
    return None


def _render_credential_meta(
    *,
    content_html: str,
    credential_tag: str,
    formatting_tags: FrozenSet[str],
    redact_passwords: bool,
) -> str:
    if credential_tag not in _CREDENTIAL_TAGS:
        raise KeyError(f"Unknown credential meta tag: {credential_tag}")
    if not isinstance(redact_passwords, bool):
        raise TypeError(f"redact_passwords must be a bool, got {type(redact_passwords)}")

    credential_meta = _CREDENTIAL_META[credential_tag]
    label_text = credential_meta["label"]
    icon_html = credential_meta["icon"]

    value_text = strip_html(content_html)
    display_text = value_text
    if credential_tag == "password" and redact_passwords:
        display_text = "X" * len(value_text)
    escaped_value = html.escape(display_text, quote=True)

    extra_classes = ""
    if formatting_tags:
        extra_classes = _meta_classes_for_tag_names(formatting_tags)

    value_class = "meta-credential-value"
    if extra_classes:
        value_class = f"{value_class} {extra_classes}"

    return (
        f'<div class="meta-credential meta-credential-{credential_tag}">'
        f'<span class="meta-credential-icon">{icon_html}</span>'
        f'<span class="meta-credential-label">{label_text}:</span>'
        f'<span class="{value_class}" data-copy-value="{escaped_value}">'
        f"{escaped_value}"
        "</span>"
        "</div>"
    )


def _render_email_meta(
    *,
    content_html: str,
    email_tag: str,
    formatting_tags: FrozenSet[str],
) -> str:
    if email_tag not in _EMAIL_TAGS:
        raise KeyError(f"Unknown email meta tag: {email_tag}")

    email_meta = _EMAIL_META[email_tag]
    label_text = email_meta["label"]
    icon_html = email_meta["icon"]

    value_text = strip_html(content_html)
    escaped_value = html.escape(value_text, quote=True)
    href_value = urllib.parse.quote(value_text, safe="@._+-")

    extra_classes = ""
    if formatting_tags:
        extra_classes = _meta_classes_for_tag_names(formatting_tags)

    value_class = "meta-email-value"
    if extra_classes:
        value_class = f"{value_class} {extra_classes}"

    return (
        '<div class="meta-email">'
        f'<span class="meta-email-icon">{icon_html}</span>'
        f'<span class="meta-email-label">{label_text}:</span>'
        f'<a class="{value_class}" href="mailto:{href_value}">{escaped_value}</a>'
        "</div>"
    )


def _find_global_status_tag(tags: str) -> str | None:
    tokens = _tokenize_tag_bar(tags)
    found_todo = False
    found_done = False
    for token in tokens:
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is not None:
            continue
        if not base.startswith("@"):
            continue
        tag_name = base[1:].casefold()
        if tag_name == "done":
            found_done = True
            continue
        if tag_name == "todo":
            found_todo = True
            continue

    if found_done:
        return "done"
    if found_todo:
        return "todo"
    return None


def _render_status_meta(
    *,
    content_html: str,
    status_tag: str,
    formatting_tags: FrozenSet[str],
) -> str:
    if status_tag not in _STATUS_TAGS:
        raise KeyError(f"Unknown status meta tag: {status_tag}")

    status_meta = _STATUS_META[status_tag]
    icon_html = status_meta["icon"]

    text_class = "meta-status-text"
    formatted_content = content_html
    if formatting_tags:
        if _should_use_box_wrapper(formatting_tags):
            formatted_content = _wrap_meta_html(
                inner_html=content_html,
                tag_names=formatting_tags,
                wrapper_class="meta-status-format",
                copy_attr="",
                allow_block_wrapper=True,
            )
        else:
            extra_classes = _meta_classes_for_tag_names(formatting_tags)
            if extra_classes:
                text_class = f"{text_class} {extra_classes}"

    return (
        f'<div class="meta-status meta-status-{status_tag}">'
        f'<span class="meta-status-toggle" data-status="{status_tag}">{icon_html}</span>'
        f'<div class="{text_class}">{formatted_content}</div>'
        "</div>"
    )


def _render_shell_meta(*, content_html: str, formatting_tags: FrozenSet[str]) -> str:
    raw_text = _extract_plain_text(content_html)
    escaped_text = html.escape(raw_text, quote=False)
    copy_attr = _copyable_attr(formatting_tags, raw_text)

    extra_classes = ""
    if formatting_tags:
        extra_classes = _meta_classes_for_tag_names(formatting_tags)

    code_class = "meta-shell-code"
    if extra_classes:
        code_class = f"{code_class} {extra_classes}"

    return (
        f'<div class="meta-shell"{copy_attr}>'
        f'<pre class="meta-shell-script"><code class="{code_class}">{escaped_text}</code></pre>'
        '<div class="meta-shell-output" aria-live="polite"></div>'
        "</div>"
    )


def _render_markdown_meta(*, content_html: str, formatting_tags: FrozenSet[str]) -> str:
    raw_text = _extract_plain_text(content_html)
    escaped_text = html.escape(raw_text, quote=False)
    copy_attr = _copyable_attr(formatting_tags, raw_text)

    extra_classes = ""
    if formatting_tags:
        extra_classes = _meta_classes_for_tag_names(formatting_tags)

    block_class = "meta-markdown"
    if extra_classes:
        block_class = f"{block_class} {extra_classes}"

    return f'<div class="{block_class}"{copy_attr}>{escaped_text}</div>'


def _render_latex_meta(*, content_html: str, formatting_tags: FrozenSet[str]) -> str:
    raw_text = _extract_plain_text(content_html)
    escaped_text = html.escape(raw_text, quote=False)
    copy_attr = _copyable_attr(formatting_tags, raw_text)

    extra_classes = ""
    if formatting_tags:
        extra_classes = _meta_classes_for_tag_names(formatting_tags)

    block_class = "meta-latex"
    if extra_classes:
        block_class = f"{block_class} {extra_classes}"

    return f'<div class="{block_class}"{copy_attr}>{escaped_text}</div>'


def _render_json_meta(*, content_html: str, formatting_tags: FrozenSet[str]) -> str:
    raw_text = _extract_plain_text(content_html)
    ok, pretty, error_message = _pretty_print_json(raw_text)
    if not ok:
        copy_attr = _copyable_attr(formatting_tags, raw_text)
        return _render_json_error(
            raw_text=raw_text,
            message=error_message,
            copy_attr=copy_attr,
        )

    highlighted = _highlight_json(pretty)
    copy_attr = _copyable_attr(formatting_tags, raw_text)

    extra_classes = ""
    if formatting_tags:
        extra_classes = _meta_classes_for_tag_names(formatting_tags)

    code_class = "meta-json-code"
    if extra_classes:
        code_class = f"{code_class} {extra_classes}"

    return (
        f'<div class="meta-json"{copy_attr}>'
        f'<pre class="meta-json-pre"><code class="{code_class}">{highlighted}</code></pre>'
        "</div>"
    )


def _render_json_error(*, raw_text: str, message: str, copy_attr: str) -> str:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")
    if not isinstance(message, str) or message == "":
        raise TypeError("message must be a non-empty string")
    if not isinstance(copy_attr, str):
        raise TypeError("copy_attr must be a string")

    escaped_message = html.escape(message, quote=True)
    escaped_text = html.escape(raw_text, quote=False)

    return (
        f'<div class="meta-json meta-json-error"{copy_attr}>'
        f'<span class="meta-json-badge" title="{escaped_message}">Invalid JSON</span>'
        f'<pre class="meta-json-pre"><code class="meta-json-code">{escaped_text}</code></pre>'
        "</div>"
    )


def _pretty_print_json(raw_text: str) -> tuple[bool, str, str]:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")

    completed = subprocess.run(
        [sys.executable, "-m", "json.tool"],
        input=raw_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        error_message = completed.stderr.strip()
        if error_message == "":
            error_message = "Invalid JSON"
        return False, "", error_message

    pretty = completed.stdout
    if pretty.endswith("\n"):
        pretty = pretty[:-1]
    pretty = _normalize_json_indent(pretty)
    return True, pretty, ""


def _normalize_json_indent(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    lines = text.splitlines()
    if not lines:
        return text

    adjusted_lines: List[str] = []
    for line in lines:
        stripped = line.lstrip(" ")
        leading_spaces = len(line) - len(stripped)
        if leading_spaces == 0:
            adjusted_lines.append(line)
            continue
        if leading_spaces % 4 != 0:
            adjusted_lines.append(line)
            continue
        indent_level = leading_spaces // 4
        adjusted_lines.append(("  " * indent_level) + stripped)

    return "\n".join(adjusted_lines)


def _extract_plain_text(content_html: str) -> str:
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")

    text = re.sub(r"<br\s*/?>", "\n", content_html, flags=re.IGNORECASE)
    text = re.sub(r"<div[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip("\n")


def _render_csv_meta(
    *,
    content_html: str,
    formatting_tags: FrozenSet[str],
    inline: bool,
    cell_wrappers: FrozenSet[Tuple[str, int]],
    cell_scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]],
    cell_scoped_renderers: Mapping[Tuple[str, int], str],
) -> str:
    raw_text = _extract_plain_text(content_html)
    copy_attr = _copyable_attr(formatting_tags, raw_text)

    placeholder_map: Dict[str, str] = {}
    parse_text = raw_text
    if cell_wrappers:
        parse_text, placeholder_map = _extract_wrapper_placeholders(
            text=raw_text,
            wrappers_to_consume=cell_wrappers,
        )

    rows, error = _parse_csv_rows(parse_text)
    if error is not None:
        return _render_csv_error(
            raw_text=raw_text,
            message=error,
            inline=inline,
            copy_attr=copy_attr,
        )

    extra_classes = ""
    if formatting_tags:
        extra_classes = _meta_classes_for_tag_names(formatting_tags)

    table_class = "meta-csv-table"
    if extra_classes:
        table_class = f"{table_class} {extra_classes}"

    meta_classes = ["meta-csv"]
    if inline:
        meta_classes.append("meta-csv-inline")

    output: List[str] = [
        f'<div class="{" ".join(meta_classes)}"{copy_attr}>',
        '<div class="meta-csv-table-wrap">',
        f'<table class="{table_class}">',
        "<tbody>",
    ]
    effective_scoped_tags = cell_scoped_tags
    apply_cell_wrappers = bool(cell_wrappers)

    for row in rows:
        output.append("<tr>")
        for cell in row:
            cell_text = cell
            if placeholder_map:
                cell_text = _restore_wrapper_placeholders(cell_text, placeholder_map)
            if apply_cell_wrappers:
                cell_html = _apply_scoped_meta_tags_to_plain_text(
                    text=cell_text,
                    wrappers_to_consume=cell_wrappers,
                    scoped_tags=effective_scoped_tags,
                    scoped_renderers=cell_scoped_renderers,
                )
            else:
                cell_html = html.escape(cell_text, quote=False)
            output.append(f"<td>{cell_html}</td>")
        output.append("</tr>")

    output.append("</tbody></table></div></div>")
    return "".join(output)


def _render_scoped_renderer(
    *,
    render_tag: str,
    content_html: str,
    formatting_tags: FrozenSet[str],
    wrappers_to_consume: FrozenSet[Tuple[str, int]],
    scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]],
    scoped_renderers: Mapping[Tuple[str, int], str],
    render_key: Tuple[str, int] | None,
) -> str:
    if render_tag == "latex":
        raw_text = _extract_plain_text(content_html)
        extra_classes = ""
        if formatting_tags:
            extra_classes = _meta_classes_for_tag_names(formatting_tags)
        return _encode_latex_placeholder(raw_text, extra_classes)
    if render_tag == "csv":
        filtered_wrappers = wrappers_to_consume
        filtered_scoped = scoped_tags
        filtered_renderers = scoped_renderers
        if render_key is not None:
            filtered_wrappers = frozenset(
                key for key in wrappers_to_consume if key != render_key
            )
            filtered_scoped = {
                key: value for key, value in scoped_tags.items() if key != render_key
            }
            filtered_renderers = {
                key: value for key, value in scoped_renderers.items() if key != render_key
            }
        return _render_csv_meta(
            content_html=content_html,
            formatting_tags=formatting_tags,
            inline=True,
            cell_wrappers=filtered_wrappers,
            cell_scoped_tags=filtered_scoped,
            cell_scoped_renderers=filtered_renderers,
        )
    raise KeyError(f"Unknown scoped renderer: {render_tag}")


def _parse_csv_rows(text: str) -> tuple[list[list[str]], str | None]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    if text.strip() == "":
        return [], "CSV is empty"

    reader = csv.reader(io.StringIO(text))
    rows = [list(row) for row in reader if not all(cell == "" for cell in row)]

    if not rows:
        return [], "CSV is empty"

    expected_len = len(rows[0])
    if expected_len == 0:
        return [], "CSV has no columns"

    for idx, row in enumerate(rows[1:], start=2):
        if len(row) != expected_len:
            return [], f"Row {idx} has {len(row)} columns, expected {expected_len}"

    return rows, None


def _render_csv_error(*, raw_text: str, message: str, inline: bool, copy_attr: str) -> str:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")
    if not isinstance(message, str) or message == "":
        raise TypeError("message must be a non-empty string")
    if not isinstance(copy_attr, str):
        raise TypeError("copy_attr must be a string")

    escaped_message = html.escape(message, quote=True)
    escaped_text = html.escape(raw_text, quote=False)
    meta_classes = ["meta-csv", "meta-csv-error"]
    if inline:
        meta_classes.append("meta-csv-inline")
    return (
        f'<div class="{" ".join(meta_classes)}"{copy_attr}>'
        f'<span class="meta-csv-badge" title="{escaped_message}">Invalid CSV</span>'
        f'<pre class="meta-csv-pre"><code class="meta-csv-code">{escaped_text}</code></pre>'
        "</div>"
    )


def _highlight_json(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    output: List[str] = []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char == '"':
            token, next_index = _consume_json_string(text, index)
            is_key = _json_string_is_key(text, next_index)
            if is_key:
                css_class = "json-key"
            else:
                css_class = "json-string"
            output.append(_wrap_json_span(css_class, token))
            index = next_index
            continue

        if char == "-" or char.isdigit():
            match = _JSON_NUMBER_RE.match(text, index)
            if match:
                token = match.group(0)
                output.append(_wrap_json_span("json-number", token))
                index = match.end()
                continue

        word_match = _match_json_word(text, index)
        if word_match is not None:
            token, css_class = word_match
            output.append(_wrap_json_span(css_class, token))
            index += len(token)
            continue

        if char in "{}[]:,":
            output.append(_wrap_json_span("json-punct", char))
            index += 1
            continue

        output.append(html.escape(char, quote=False))
        index += 1

    return "".join(output)


def _consume_json_string(text: str, start: int) -> tuple[str, int]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(start, int) or start < 0:
        raise TypeError("start must be a non-negative integer")

    index = start + 1
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            index += 1
            break
        index += 1
    return text[start:index], index


def _json_string_is_key(text: str, index: int) -> bool:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(index, int) or index < 0:
        raise TypeError("index must be a non-negative integer")

    probe = index
    length = len(text)
    while probe < length and text[probe].isspace():
        probe += 1
    return probe < length and text[probe] == ":"


def _match_json_word(text: str, index: int) -> tuple[str, str] | None:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(index, int) or index < 0:
        raise TypeError("index must be a non-negative integer")

    for word, css_class in (("true", "json-boolean"), ("false", "json-boolean"), ("null", "json-null")):
        if text.startswith(word, index):
            end = index + len(word)
            if end == len(text) or not text[end].isalpha():
                return word, css_class
    return None


def _wrap_json_span(css_class: str, token: str) -> str:
    if not isinstance(css_class, str) or css_class == "":
        raise TypeError("css_class must be a non-empty string")
    if not isinstance(token, str):
        raise TypeError("token must be a string")
    return f'<span class="{css_class}">{html.escape(token, quote=False)}</span>'


def _copyable_attr(formatting_tags: FrozenSet[str], raw_text: str) -> str:
    if "copyable" not in formatting_tags:
        return ""
    escaped_text = html.escape(raw_text, quote=True)
    return f' data-copy-value="{escaped_text}"'


def _should_use_box_wrapper(tag_names: Set[str] | FrozenSet[str]) -> bool:
    return "strikethrough" in tag_names


def _html_contains_block_elements(content_html: str) -> bool:
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")
    return _BLOCK_HTML_TAG_RE.search(content_html) is not None


def _wrap_meta_html(
    *,
    inner_html: str,
    tag_names: Set[str] | FrozenSet[str],
    wrapper_class: str,
    copy_attr: str,
    allow_block_wrapper: bool,
) -> str:
    if not isinstance(inner_html, str):
        raise TypeError("inner_html must be a string")
    if not isinstance(wrapper_class, str) or wrapper_class == "":
        raise TypeError("wrapper_class must be a non-empty string")
    if not isinstance(copy_attr, str):
        raise TypeError("copy_attr must be a string")

    classes = _meta_classes_for_tag_names(tag_names)
    if classes == "":
        raise AssertionError("Formatted wrapper requires at least one CSS class")

    class_names: List[str] = [wrapper_class]
    wrapper_tag = "span"
    if _should_use_box_wrapper(tag_names):
        if allow_block_wrapper and _html_contains_block_elements(inner_html):
            wrapper_tag = "div"
            class_names.append("meta-box-block")
        else:
            class_names.append("meta-box-inline")
    class_names.append(classes)
    class_attr = " ".join(class_names)
    return f'<{wrapper_tag} class="{class_attr}"{copy_attr}>{inner_html}</{wrapper_tag}>'


def _encode_latex_placeholder(raw_text: str, extra_classes: str) -> str:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")
    if not isinstance(extra_classes, str):
        raise TypeError("extra_classes must be a string")
    payload = {"text": raw_text, "classes": extra_classes}
    encoded = base64.b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).decode("ascii")
    return f"{_LATEX_PLACEHOLDER_PREFIX}{encoded}{_LATEX_PLACEHOLDER_SUFFIX}"


def _parse_meta_tags(tags: str) -> MetaTagConfig:
    tokens = _tokenize_tag_bar(tags)
    global_tags: Set[str] = set()
    wrappers_to_consume: Set[Tuple[str, int]] = set()
    scoped: Dict[Tuple[str, int], Set[str]] = {}
    scoped_renderers: Dict[Tuple[str, int], str] = {}

    for token in tokens:
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is None:
            if not base.startswith("@"):
                continue
            tag_name = base[1:].casefold()
            if tag_name not in _META_TAG_TO_CLASS:
                continue
            global_tags.add(tag_name)
            continue

        inner_tokens = [inner for inner in base.split() if inner]
        if not inner_tokens:
            continue

        opener, depth = wrapper
        key = (opener, depth)
        wrappers_to_consume.add(key)
        for inner in inner_tokens:
            if not inner.startswith("@"):
                continue
            tag_name = inner[1:].casefold()
            if tag_name not in _META_TAG_TO_CLASS:
                if tag_name in {"csv", "latex"}:
                    existing = None
                    if key in scoped_renderers:
                        existing = scoped_renderers[key]
                    if existing is not None and existing != tag_name:
                        raise ValueError(
                            f"Wrapper {key} has conflicting scoped renderers: {existing} vs {tag_name}"
                        )
                    scoped_renderers[key] = tag_name
                continue
            if key not in scoped:
                scoped[key] = set()
            scoped[key].add(tag_name)

    frozen_scoped: Dict[Tuple[str, int], FrozenSet[str]] = {
        key: frozenset(value) for key, value in scoped.items()
    }
    return MetaTagConfig(
        global_tags=frozenset(global_tags),
        wrappers_to_consume=frozenset(wrappers_to_consume),
        scoped_tags=frozen_scoped,
        scoped_renderers=dict(scoped_renderers),
    )


def _tokenize_tag_bar(tags: str) -> List[str]:
    tokens: List[str] = []
    index = 0
    while index < len(tags):
        while index < len(tags) and tags[index].isspace():
            index += 1
        if index >= len(tags):
            break

        if tags.startswith("/*", index):
            end = tags.find("*/", index + 2)
            if end == -1:
                break
            index = end + 2
            continue

        start = index
        opener = tags[index]
        if opener in _OPEN_TO_CLOSE:
            opener_run = 1
            while index + opener_run < len(tags) and tags[index + opener_run] == opener:
                opener_run += 1
            if opener_run <= _MAX_DELIMITER_DEPTH:
                closer = _OPEN_TO_CLOSE[opener]
                needle = closer * opener_run
                close_at = tags.find(needle, index + opener_run)
                if close_at != -1:
                    index = close_at + opener_run
                    token = tags[start:index]
                    if token:
                        tokens.append(token)
                    continue

        while index < len(tags) and not tags[index].isspace():
            index += 1
        token = tags[start:index]
        if token:
            tokens.append(token)
    return tokens


def _unwrap_tag_token(token: str) -> Tuple[str, Tuple[str, int] | None]:
    if not token:
        return token, None

    opener = token[0]
    if opener not in _OPEN_TO_CLOSE:
        return token, None

    opener_run = 1
    while opener_run < len(token) and token[opener_run] == opener:
        opener_run += 1
    if opener_run > _MAX_DELIMITER_DEPTH:
        return token, None
    depth = opener_run

    closer = _OPEN_TO_CLOSE[opener]
    if len(token) < depth * 2:
        return token, None

    if token[-1] != closer:
        return token, None

    closer_run = 1
    while closer_run < len(token) and token[-(closer_run + 1)] == closer:
        closer_run += 1
    if closer_run != depth:
        return token, None

    if token[-depth:] != closer * depth:
        return token, None

    inner = token[depth:-depth]
    if not inner:
        return token, None

    return inner, (opener, depth)


@dataclass(slots=True)
class _OpenFrame:
    opener: str
    closer: str
    depth: int
    placeholder_index: int
    opener_text: str
    open_html: str
    close_html: str
    render_tag: str | None
    formatting_tags: FrozenSet[str] | None
    render_key: Tuple[str, int] | None


def _apply_scoped_meta_tags(
    *,
    content_html: str,
    wrappers_to_consume: FrozenSet[Tuple[str, int]],
    scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]],
    scoped_renderers: Mapping[Tuple[str, int], str],
) -> str:
    parts = re.split(r"(<[^>]+>)", content_html)
    output: List[str] = []
    stack: List[_OpenFrame] = []

    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            output.append(part)
            continue
        _process_text_segment(
            text=part,
            output=output,
            stack=stack,
            wrappers_to_consume=wrappers_to_consume,
            scoped_tags=scoped_tags,
            scoped_renderers=scoped_renderers,
            escape_text=False,
        )

    for frame in stack:
        output[frame.placeholder_index] = frame.opener_text

    return "".join(output)


def _apply_scoped_meta_tags_to_plain_text(
    *,
    text: str,
    wrappers_to_consume: FrozenSet[Tuple[str, int]],
    scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]],
    scoped_renderers: Mapping[Tuple[str, int], str],
) -> str:
    output: List[str] = []
    stack: List[_OpenFrame] = []
    _process_text_segment(
        text=text,
        output=output,
        stack=stack,
        wrappers_to_consume=wrappers_to_consume,
        scoped_tags=scoped_tags,
        scoped_renderers=scoped_renderers,
        escape_text=True,
    )
    for frame in stack:
        output[frame.placeholder_index] = frame.opener_text
    return "".join(output)


def _process_text_segment(
    *,
    text: str,
    output: List[str],
    stack: List[_OpenFrame],
    wrappers_to_consume: FrozenSet[Tuple[str, int]],
    scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]],
    scoped_renderers: Mapping[Tuple[str, int], str],
    escape_text: bool,
) -> None:
    index = 0
    while index < len(text):
        char = text[index]
        active_renderer: _OpenFrame | None = None
        for frame in reversed(stack):
            if frame.render_tag is not None:
                active_renderer = frame
                break
        if active_renderer is not None:
            run = 1
            if char in _OPEN_TO_CLOSE or char in _CLOSE_TO_OPEN:
                run = _count_run(text=text, index=index, char=char)
            if char in _CLOSE_TO_OPEN:
                if run <= _MAX_DELIMITER_DEPTH:
                    if active_renderer.closer == char and active_renderer.depth == run:
                        stack.pop()
                        inner_parts = output[active_renderer.placeholder_index + 1 :]
                        inner_html = "".join(inner_parts)
                        formatting_tags = active_renderer.formatting_tags
                        if formatting_tags is None:
                            formatting_tags = frozenset()
                        rendered = _render_scoped_renderer(
                            render_tag=active_renderer.render_tag,
                            content_html=inner_html,
                            formatting_tags=formatting_tags,
                            wrappers_to_consume=wrappers_to_consume,
                            scoped_tags=scoped_tags,
                            scoped_renderers=scoped_renderers,
                            render_key=active_renderer.render_key,
                        )
                        del output[active_renderer.placeholder_index :]
                        output.append(rendered)
                        index += run
                        continue
            segment = text[index : index + run]
            if escape_text:
                output.append(html.escape(segment, quote=False))
            else:
                output.append(segment)
            index += run
            continue
        if char in _OPEN_TO_CLOSE:
            run = _count_run(text=text, index=index, char=char)
            if run <= _MAX_DELIMITER_DEPTH and (char, run) in wrappers_to_consume:
                key = (char, run)
                open_html = ""
                close_html = ""
                render_tag = None
                formatting_tags = None
                render_key = None
                if key in scoped_renderers:
                    render_tag = scoped_renderers[key]
                    if key in scoped_tags:
                        formatting_tags = scoped_tags[key]
                    else:
                        formatting_tags = frozenset()
                    render_key = key
                if key in scoped_tags:
                    formatting_tags = scoped_tags[key]
                    classes = _meta_classes_for_tag_names(scoped_tags[key])
                    assert classes, "Scoped meta tags must resolve to at least one CSS class"
                    open_html = f'<span class="meta-scope {classes}">'
                    close_html = "</span>"
                opener_text = text[index : index + run]
                placeholder_index = len(output)
                output.append("")
                stack.append(
                    _OpenFrame(
                        opener=char,
                        closer=_OPEN_TO_CLOSE[char],
                        depth=run,
                        placeholder_index=placeholder_index,
                        opener_text=opener_text,
                        open_html=open_html,
                        close_html=close_html,
                        render_tag=render_tag,
                        formatting_tags=formatting_tags,
                        render_key=render_key,
                    )
                )
                index += run
                continue
            segment = text[index : index + run]
            if escape_text:
                output.append(html.escape(segment, quote=False))
            else:
                output.append(segment)
            index += run
            continue

        if char in _CLOSE_TO_OPEN:
            run = _count_run(text=text, index=index, char=char)
            if run <= _MAX_DELIMITER_DEPTH and stack:
                top = stack[-1]
                if top.closer == char and top.depth == run:
                    stack.pop()
                    if (
                        top.render_tag is None
                        and top.formatting_tags is not None
                        and _should_use_box_wrapper(top.formatting_tags)
                    ):
                        inner_parts = output[top.placeholder_index + 1 :]
                        inner_html = "".join(inner_parts)
                        if not _html_contains_block_elements(inner_html):
                            rendered = _wrap_meta_html(
                                inner_html=inner_html,
                                tag_names=top.formatting_tags,
                                wrapper_class="meta-scope",
                                copy_attr="",
                                allow_block_wrapper=False,
                            )
                            del output[top.placeholder_index :]
                            output.append(rendered)
                            index += run
                            continue
                    output[top.placeholder_index] = top.open_html
                    output.append(top.close_html)
                    index += run
                    continue
            segment = text[index : index + run]
            if escape_text:
                output.append(html.escape(segment, quote=False))
            else:
                output.append(segment)
            index += run
            continue

        if escape_text:
            output.append(html.escape(char, quote=False))
        else:
            output.append(char)
        index += 1


def _count_run(*, text: str, index: int, char: str) -> int:
    run = 1
    while index + run < len(text) and text[index + run] == char:
        run += 1
    return run


def _extract_wrapper_placeholders(
    *,
    text: str,
    wrappers_to_consume: FrozenSet[Tuple[str, int]],
) -> tuple[str, Dict[str, str]]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    if not wrappers_to_consume:
        return text, {}

    output: List[str] = []
    placeholders: Dict[str, str] = {}
    stack: List[Dict[str, object]] = []
    index = 0
    placeholder_index = 0

    while index < len(text):
        char = text[index]

        if char in _OPEN_TO_CLOSE:
            run = _count_run(text=text, index=index, char=char)
            key = (char, run)
            if run <= _MAX_DELIMITER_DEPTH and key in wrappers_to_consume:
                stack.append({
                    "opener": char,
                    "closer": _OPEN_TO_CLOSE[char],
                    "depth": run,
                    "content": [],
                })
                index += run
                continue

        if char in _CLOSE_TO_OPEN:
            run = _count_run(text=text, index=index, char=char)
            if run <= _MAX_DELIMITER_DEPTH and stack:
                top = stack[-1]
                if top["closer"] == char and top["depth"] == run:
                    stack.pop()
                    inner = "".join(top["content"])
                    opener_text = str(top["opener"]) * int(top["depth"])
                    closer_text = char * run
                    original = f"{opener_text}{inner}{closer_text}"
                    placeholder = f"@@CSV_WRAPPER_{placeholder_index}@@"
                    placeholder_index += 1
                    placeholders[placeholder] = original
                    if stack:
                        stack[-1]["content"].append(placeholder)
                    else:
                        output.append(placeholder)
                    index += run
                    continue

        if stack:
            target = stack[-1]["content"]
        else:
            target = output
        target.append(char)
        index += 1

    if stack:
        return text, {}

    return "".join(output), placeholders


def _restore_wrapper_placeholders(text: str, placeholders: Dict[str, str]) -> str:
    if not placeholders:
        return text

    output = text
    replaced = True
    while replaced:
        replaced = False
        for key, value in placeholders.items():
            if key in output:
                output = output.replace(key, value)
                replaced = True
    return output


def _meta_classes_for_tag_names(tag_names: Set[str] | FrozenSet[str]) -> str:
    classes: List[str] = []
    for name in sorted(tag_names):
        if name not in _META_TAG_TO_CLASS:
            raise KeyError(f"Unknown meta tag name: {name}")
        css_class = _META_TAG_TO_CLASS[name]
        classes.append(css_class)
    return " ".join(classes)
