"""Small provider-neutral estimates for diagnostic input-size feedback."""

from __future__ import annotations

import json


_APPROXIMATE_CHARACTERS_PER_TOKEN = 4


def estimate_input_tokens(value: object) -> int:
    """Estimate tokens from the compact JSON representation sent or retained."""
    serialized_value = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    character_count = len(serialized_value)
    return max(
        1,
        (character_count + _APPROXIMATE_CHARACTERS_PER_TOKEN - 1)
        // _APPROXIMATE_CHARACTERS_PER_TOKEN,
    )
