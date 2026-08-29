"""Provider-neutral token estimates for budgets and diagnostic feedback."""

from __future__ import annotations

import json
import unicodedata


def estimate_text_tokens(text: str) -> int:
    """Estimate tokenizer cost without binding the harness to one model family."""
    if not isinstance(text, str):
        raise TypeError("Token estimation text must be a string")
    if text == "":
        return 1

    estimate = 0
    index = 0
    while index < len(text):
        character = text[index]
        if character.isascii() and character.isalpha():
            end = index + 1
            while end < len(text) and text[end].isascii() and text[end].isalpha():
                end += 1
            run_length = end - index
            estimate += max(1, (run_length + 2) // 4)
            index = end
            continue
        if character.isascii() and character.isdecimal():
            end = index + 1
            while end < len(text) and text[end].isascii() and text[end].isdecimal():
                end += 1
            run_length = end - index
            estimate += (run_length + 2) // 3
            index = end
            continue
        if character.isspace():
            if character in {"\n", "\r", "\t"}:
                estimate += 1
            index += 1
            continue
        if character.isascii():
            estimate += 1
            index += 1
            continue

        end = index + 1
        while end < len(text):
            candidate = text[end]
            if candidate.isascii() or candidate.isspace():
                break
            if unicodedata.category(candidate).startswith("P"):
                break
            end += 1
        utf8_byte_count = len(text[index:end].encode("utf-8"))
        estimate += max(1, (utf8_byte_count + 2) // 3)
        index = end

    return max(1, estimate)


def estimate_input_tokens(value: object) -> int:
    """Estimate tokens from the compact JSON representation sent or retained."""
    serialized_value = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return estimate_text_tokens(serialized_value)
