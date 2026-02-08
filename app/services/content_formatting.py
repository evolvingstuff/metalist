from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Mapping, Set, Tuple

from app.utils.text_utils import strip_html


_OPEN_TO_CLOSE = {
    "[": "]",
    "{": "}",
    "(": ")",
}
_CLOSE_TO_OPEN = {value: key for key, value in _OPEN_TO_CLOSE.items()}

_MAX_DELIMITER_DEPTH = 3

_META_TAG_TO_CLASS = {
    "monospace": "meta-monospace",
    "red": "meta-red",
}

_CREDENTIAL_TAGS = frozenset({"username", "password"})

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

@dataclass(frozen=True, slots=True)
class MetaTagConfig:
    global_tags: FrozenSet[str]
    wrappers_to_consume: FrozenSet[Tuple[str, int]]
    scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]]


def format_note_content_for_view(*, content_html: str, tags: str) -> str:
    if not isinstance(content_html, str):
        raise TypeError(f"content_html must be a string, got {type(content_html)}")
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")

    config = _parse_meta_tags(tags)
    credential_tag = _find_global_credential_tag(tags)
    status_tag = _find_global_status_tag(tags)
    json_tag = _find_global_json_tag(tags)
    if json_tag is not None:
        return _render_json_meta(
            content_html=content_html,
            formatting_tags=config.global_tags,
        )

    if not config.global_tags and not config.wrappers_to_consume and credential_tag is None and status_tag is None:
        return content_html

    output = content_html
    if config.wrappers_to_consume:
        output = _apply_scoped_meta_tags(
            content_html=output,
            wrappers_to_consume=config.wrappers_to_consume,
            scoped_tags=config.scoped_tags,
        )

    if credential_tag is not None:
        return _render_credential_meta(
            content_html=output,
            credential_tag=credential_tag,
            formatting_tags=config.global_tags,
        )

    if status_tag is not None:
        return _render_status_meta(
            content_html=output,
            status_tag=status_tag,
            formatting_tags=config.global_tags,
        )

    if config.global_tags:
        classes = _meta_classes_for_tag_names(config.global_tags)
        if classes:
            output = f'<span class="meta-global {classes}">{output}</span>'

    return output


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
        tag_name = base[1:]
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


def _render_credential_meta(
    *,
    content_html: str,
    credential_tag: str,
    formatting_tags: FrozenSet[str],
) -> str:
    if credential_tag not in _CREDENTIAL_TAGS:
        raise KeyError(f"Unknown credential meta tag: {credential_tag}")

    credential_meta = _CREDENTIAL_META[credential_tag]
    label_text = credential_meta["label"]
    icon_html = credential_meta["icon"]

    value_text = strip_html(content_html)
    escaped_value = html.escape(value_text, quote=True)

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
        tag_name = base[1:]
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

    extra_classes = ""
    if formatting_tags:
        extra_classes = _meta_classes_for_tag_names(formatting_tags)

    text_class = "meta-status-text"
    if extra_classes:
        text_class = f"{text_class} {extra_classes}"

    return (
        f'<div class="meta-status meta-status-{status_tag}">'
        f'<span class="meta-status-toggle" data-status="{status_tag}">{icon_html}</span>'
        f'<div class="{text_class}">{content_html}</div>'
        "</div>"
    )


def _find_global_json_tag(tags: str) -> str | None:
    tokens = _tokenize_tag_bar(tags)
    for token in tokens:
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is not None:
            continue
        if base == "@json":
            return "json"
    return None


def _render_json_meta(*, content_html: str, formatting_tags: FrozenSet[str]) -> str:
    raw_text = _extract_json_text(content_html)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return _render_json_error(raw_text, exc)

    pretty = json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=False)
    highlighted = _highlight_json(pretty)

    extra_classes = ""
    if formatting_tags:
        extra_classes = _meta_classes_for_tag_names(formatting_tags)

    code_class = "meta-json-code"
    if extra_classes:
        code_class = f"{code_class} {extra_classes}"

    return (
        '<div class="meta-json">'
        f'<pre class="meta-json-pre"><code class="{code_class}">{highlighted}</code></pre>'
        "</div>"
    )


def _render_json_error(raw_text: str, error: json.JSONDecodeError) -> str:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")
    if not isinstance(error, json.JSONDecodeError):
        raise TypeError("error must be a JSONDecodeError")

    message = _format_json_error(error)
    escaped_message = html.escape(message, quote=True)
    escaped_text = html.escape(raw_text, quote=False)

    return (
        '<div class="meta-json meta-json-error">'
        f'<span class="meta-json-badge" title="{escaped_message}">Invalid JSON</span>'
        f'<pre class="meta-json-pre"><code class="meta-json-code">{escaped_text}</code></pre>'
        "</div>"
    )


def _format_json_error(error: json.JSONDecodeError) -> str:
    return f"Line {error.lineno}, column {error.colno}: {error.msg}"


def _extract_json_text(content_html: str) -> str:
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")

    text = re.sub(r"<br\s*/?>", "\n", content_html, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<div[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


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
            css_class = "json-key" if is_key else "json-string"
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


def _parse_meta_tags(tags: str) -> MetaTagConfig:
    tokens = _tokenize_tag_bar(tags)
    global_tags: Set[str] = set()
    wrappers_to_consume: Set[Tuple[str, int]] = set()
    scoped: Dict[Tuple[str, int], Set[str]] = {}

    for token in tokens:
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is None:
            if not base.startswith("@"):
                continue
            tag_name = base[1:]
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
            tag_name = inner[1:]
            if tag_name not in _META_TAG_TO_CLASS:
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


def _apply_scoped_meta_tags(
    *,
    content_html: str,
    wrappers_to_consume: FrozenSet[Tuple[str, int]],
    scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]],
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
) -> None:
    index = 0
    while index < len(text):
        char = text[index]
        if char in _OPEN_TO_CLOSE:
            run = _count_run(text=text, index=index, char=char)
            if run <= _MAX_DELIMITER_DEPTH and (char, run) in wrappers_to_consume:
                key = (char, run)
                open_html = ""
                close_html = ""
                if key in scoped_tags:
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
                    )
                )
                index += run
                continue
            output.append(text[index : index + run])
            index += run
            continue

        if char in _CLOSE_TO_OPEN:
            run = _count_run(text=text, index=index, char=char)
            if run <= _MAX_DELIMITER_DEPTH and stack:
                top = stack[-1]
                if top.closer == char and top.depth == run:
                    stack.pop()
                    output[top.placeholder_index] = top.open_html
                    output.append(top.close_html)
                    index += run
                    continue
            output.append(text[index : index + run])
            index += run
            continue

        output.append(char)
        index += 1


def _count_run(*, text: str, index: int, char: str) -> int:
    run = 1
    while index + run < len(text) and text[index + run] == char:
        run += 1
    return run


def _meta_classes_for_tag_names(tag_names: Set[str] | FrozenSet[str]) -> str:
    classes: List[str] = []
    for name in sorted(tag_names):
        if name not in _META_TAG_TO_CLASS:
            raise KeyError(f"Unknown meta tag name: {name}")
        css_class = _META_TAG_TO_CLASS[name]
        classes.append(css_class)
    return " ".join(classes)
