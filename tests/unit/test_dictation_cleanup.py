"""Cleaning up dictated text pasted into the search bar or the tag bar.

Each case is one agreed behavior (see docs/ui/dictation-paste.md): text from a
speech-to-text tool such as Superwhisper becomes the user's existing tags.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

import app.api.routes.notes as notes_route
from app.services.dictation_cleanup import KNOWN_META_TAGS, clean_dictated_paste


TAGS = {
    "neural-network": 5,
    "Neural-Network": 1,
    "neural": 1,
    "network": 1,
    "python": 3,
    "GPT": 2,
    "transformer": 1,
    "foo-bar": 1,
}


def _clean(text: str, *, target: str, current: str, tags: dict[str, int]) -> str:
    return clean_dictated_paste(text=text, target=target, existing_tag_frequencies=tags, current_value=current)


def _search(text: str) -> str:
    return _clean(text, target="search", current="", tags=TAGS)


def _tags(text: str) -> str:
    return _clean(text, target="tags", current="", tags=TAGS)


@pytest.mark.parametrize("pasted,expected", [
    # The reported example: punctuation, sentence case, repeats and "Neural-Dash".
    ("Neural network, neural network. Neural-Dash Network.", "neural-network"),
    ("Neural network and python", "neural-network python"),
    # Unknown words are dropped in search.
    ("Neural network transformers", "neural-network"),
    ("Quote attention is all you need end quote neural network", '"attention is all you need" neural-network'),
    ("quote attention is all you need unquote python", '"attention is all you need" python'),
    ("“attention is all you need” python", '"attention is all you need" python'),
    ("Neural network or python.", "neural-network OR python"),
    ("Neural network, not python.", "neural-network -python"),
    ("Minus python neural network", "-python neural-network"),
    # Operators with nothing to apply to are dropped.
    ("Or python", "python"),
    ("Python or", "python"),
    ("Python or bananas", "python"),
    ("Not bananas python", "python"),
    ("And the.", ""),
    # Already-valid search syntax is kept as it is.
    ("neural-network -python", "neural-network -python"),
    ('neural-network OR "exact words"', 'neural-network OR "exact words"'),
])
def test_search_cases(pasted: str, expected: str) -> None:
    assert _search(pasted) == expected


@pytest.mark.parametrize("pasted,expected", [
    ("Neural network, transformers.", "neural-network transformers"),
    ("gpt and the transformer", "GPT transformer"),
    ("Quote machine learning end quote", "machine-learning"),
    ("Quote neural network end quote", "neural-network"),
    ("neural-network python", "neural-network python"),
    # New tags are lowercased unless they look like an acronym.
    ("LLM Evaluation", "LLM evaluation"),
    # Spoken operators are filler in the tag bar.
    ("Python or neural network, not GPT", "python neural-network GPT"),
])
def test_tag_bar_cases(pasted: str, expected: str) -> None:
    assert _tags(pasted) == expected


@pytest.mark.parametrize("pasted", [
    # How Superwhisper writes "foo dash bar", and its variations.
    "foo-Dash bar",
    "Foo-Dash Bar.",
    "foo-dash bar",
    "foo -Dash bar",
    "foo - Dash bar",
    "foo dash bar",
    "foo-Hyphen bar",
    "foo hyphen bar",
])
def test_spoken_dash_joins_words(pasted: str) -> None:
    assert _search(pasted) == "foo-bar"
    assert _clean(pasted, target="tags", current="", tags={}) == "foo-bar"


@pytest.mark.parametrize("pasted,expected", [
    ("foo_Underscore bar", "foo_bar"),
    ("foo underscore bar", "foo_bar"),
    ("foo/Slash bar", "foo/bar"),
    ("foo slash bar", "foo/bar"),
])
def test_other_spoken_joiners(pasted: str, expected: str) -> None:
    assert _clean(pasted, target="tags", current="", tags={}) == expected


def test_the_longest_matching_phrase_wins_and_uses_the_most_used_spelling() -> None:
    # neural, network and neural-network all exist: the phrase is one tag, spelled
    # the way it is used most (neural-network 5 times, Neural-Network once).
    assert _search("NEURAL NETWORK") == "neural-network"


def test_a_spoken_word_that_is_a_tag_stays_a_tag() -> None:
    tags = {**TAGS, "not": 2, "and": 1, "tags": 1}
    assert _clean("not python", target="search", current="", tags=tags) == "not python"
    assert _clean("python and tags", target="tags", current="", tags=tags) == "python and tags"


def test_minus_is_an_operator_only_when_spelled_out_and_not_a_tag() -> None:
    assert _clean("minus python", target="search", current="", tags={**TAGS, "minus": 1}) == "minus python"
    assert _search("minus python") == "-python"


def test_tags_already_in_the_field_are_not_added_again() -> None:
    assert _clean("python GPT", target="tags", current="python", tags=TAGS) == "GPT"
    assert _clean("Neural network", target="tags", current="neural-network", tags=TAGS) == ""
    assert _clean("python neural network", target="search", current="python", tags=TAGS) == "neural-network"


def test_target_must_be_search_or_tags() -> None:
    with pytest.raises(ValueError):
        clean_dictated_paste(text="python", target="notes", existing_tag_frequencies=TAGS, current_value="")


class _FakeSearchIndex:
    def list_explicit_tag_frequencies(self) -> dict[str, int]:
        return dict(TAGS)


def test_the_endpoint_cleans_against_the_namespace_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notes_route, "search_index", _FakeSearchIndex())
    payload = {"text": "Neural network, neural network. Neural-Dash Network.", "target": "search", "current_value": ""}
    assert notes_route.dictation_paste(payload) == {"text": "neural-network"}


# Words run together: a phrase also matches a tag written as one word.
@pytest.mark.parametrize("pasted,tags,expected", [
    ("To do.", {"todo": 1}, "todo"),
    ("super whisper", {"superwhisper": 2}, "superwhisper"),
    ("Note book, python", {"notebook": 1, "python": 1}, "notebook python"),
    # Keeping the joiner wins over running the words together.
    ("to do", {"to-do": 1, "todo": 5}, "to-do"),
])
def test_spoken_words_match_a_one_word_tag(pasted: str, tags: dict[str, int], expected: str) -> None:
    assert _clean(pasted, target="search", current="", tags=tags) == expected
    assert _clean(pasted, target="tags", current="", tags=tags) == expected


# "at" (or a typed @) before a built-in meta tag is that meta tag.
@pytest.mark.parametrize("pasted,expected", [
    ("at to do", "@todo"),
    ("At todo.", "@todo"),
    ("@ to do", "@todo"),
    ("@todo", "@todo"),
    ("at done", "@done"),
    ("at list bulleted", "@list-bulleted"),
    ("At list-bulleted", "@list-bulleted"),
    ("At heading, at red.", "@heading @red"),
    ("neural network at to do", "neural-network @todo"),
])
def test_at_before_a_meta_tag_is_that_meta_tag(pasted: str, expected: str) -> None:
    assert _search(pasted) == expected
    assert _tags(pasted) == expected


def test_at_is_filler_unless_it_starts_a_meta_tag_or_is_a_tag() -> None:
    assert _tags("meeting at noon") == "meeting noon"
    assert _search("python at noon") == "python"
    assert _clean("meeting at noon", target="tags", current="", tags={"at": 1}) == "meeting at noon"
    # Not a meta tag: "at" is dropped and the words stay words.
    assert _tags("at foo") == "foo"


def test_the_meta_tag_list_matches_the_browser() -> None:
    source = (Path(__file__).resolve().parents[2]
              / "app/static/js/modules/mode-manager/services/tag-syntax-service.js").read_text(encoding="utf-8")
    block = re.search(r"const KNOWN_META_TAGS = new Set\(\[(.*?)\]\);", source, re.DOTALL)
    assert block is not None
    assert set(re.findall(r"'(@[^']+)'", block.group(1))) == set(KNOWN_META_TAGS)


def test_tags_dictated_alone_into_a_note_match_a_one_word_tag() -> None:
    # "Start tags, scratch pad." pasted into a note: the words after the phrase.
    assert _clean("scratch pad.", target="tags", current="python", tags={"scratchpad": 4}) == "scratchpad"
