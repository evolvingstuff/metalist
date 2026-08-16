from __future__ import annotations

import pytest

from app.services.selected_text_tag import (
    SelectedTextTagValidationError,
    build_default_tag_from_selected_text,
    find_equivalent_existing_tag,
)


def test_build_default_tag_preserves_case_and_joins_whitespace() -> None:
    assert build_default_tag_from_selected_text("Neural Networks") == "Neural-Networks"
    assert build_default_tag_from_selected_text("  GPT\nModels  ") == "GPT-Models"


def test_build_default_tag_removes_illegal_tag_characters() -> None:
    assert build_default_tag_from_selected_text("<Neural> Networks") == "Neural-Networks"
    assert build_default_tag_from_selected_text("+C++") == "C++"
    assert build_default_tag_from_selected_text("Tag, Give") == "Tag-Give"


def test_build_default_tag_rejects_long_or_empty_sanitized_selection() -> None:
    with pytest.raises(SelectedTextTagValidationError, match="25 characters or fewer"):
        build_default_tag_from_selected_text("a" * 26)

    with pytest.raises(SelectedTextTagValidationError, match="usable tag characters"):
        build_default_tag_from_selected_text("<<<>>>")


def test_build_default_tag_rejects_reserved_or_operator() -> None:
    with pytest.raises(SelectedTextTagValidationError, match="reserved for search"):
        build_default_tag_from_selected_text("OR")

    assert build_default_tag_from_selected_text("or") == "or"


def test_find_equivalent_existing_tag_matches_case_and_joiner_variants() -> None:
    existing = {
        "Neural.Networks": 2,
        "neural_networks": 5,
        "neural/networks": 3,
        "unrelated": 20,
    }

    assert find_equivalent_existing_tag(
        selected_text="Neural Networks",
        existing_tag_frequencies=existing,
    ) == "neural_networks"
    assert find_equivalent_existing_tag(
        selected_text="(Neural Networks)",
        existing_tag_frequencies=existing,
    ) == "neural_networks"


def test_find_equivalent_existing_tag_does_not_ignore_non_joining_punctuation() -> None:
    assert find_equivalent_existing_tag(
        selected_text="Hello!",
        existing_tag_frequencies={"hello": 10},
    ) is None
