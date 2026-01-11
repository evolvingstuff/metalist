from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Mapping, Set, Tuple


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


@dataclass(frozen=True, slots=True)
class MetaTagConfig:
    global_tags: FrozenSet[str]
    scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]]


def format_note_content_for_view(*, content_html: str, tags: str) -> str:
    if not isinstance(content_html, str):
        raise TypeError(f"content_html must be a string, got {type(content_html)}")
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")

    config = _parse_meta_tags(tags)
    if not config.global_tags and not config.scoped_tags:
        return content_html

    output = content_html
    if config.scoped_tags:
        output = _apply_scoped_meta_tags(content_html=output, scoped_tags=config.scoped_tags)

    if config.global_tags:
        classes = _meta_classes_for_tag_names(config.global_tags)
        if classes:
            output = f'<span class="meta-global {classes}">{output}</span>'

    return output


def _parse_meta_tags(tags: str) -> MetaTagConfig:
    tokens = _tokenize_tag_bar(tags)
    global_tags: Set[str] = set()
    scoped: Dict[Tuple[str, int], Set[str]] = {}

    for token in tokens:
        base, wrapper = _unwrap_tag_token(token)
        if not base.startswith("@"):
            continue

        tag_name = base[1:]
        if tag_name not in _META_TAG_TO_CLASS:
            continue

        if wrapper is None:
            global_tags.add(tag_name)
            continue

        opener, depth = wrapper
        key = (opener, depth)
        if key not in scoped:
            scoped[key] = set()
        scoped[key].add(tag_name)

    frozen_scoped: Dict[Tuple[str, int], FrozenSet[str]] = {
        key: frozenset(value) for key, value in scoped.items()
    }
    return MetaTagConfig(global_tags=frozenset(global_tags), scoped_tags=frozen_scoped)


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


def _apply_scoped_meta_tags(*, content_html: str, scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]]) -> str:
    parts = re.split(r"(<[^>]+>)", content_html)
    output: List[str] = []
    stack: List[_OpenFrame] = []

    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            output.append(part)
            continue
        _process_text_segment(text=part, output=output, stack=stack, scoped_tags=scoped_tags)

    for frame in stack:
        output[frame.placeholder_index] = frame.opener_text

    return "".join(output)


def _process_text_segment(
    *,
    text: str,
    output: List[str],
    stack: List[_OpenFrame],
    scoped_tags: Mapping[Tuple[str, int], FrozenSet[str]],
) -> None:
    index = 0
    while index < len(text):
        char = text[index]
        if char in _OPEN_TO_CLOSE:
            run = _count_run(text=text, index=index, char=char)
            if run <= _MAX_DELIMITER_DEPTH and (char, run) in scoped_tags:
                tag_names = scoped_tags[(char, run)]
                classes = _meta_classes_for_tag_names(tag_names)
                assert classes, "Scoped meta tags must resolve to at least one CSS class"
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
                        open_html=f'<span class="meta-scope {classes}">',
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
                    output.append("</span>")
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
