from __future__ import annotations

import pytest

from app.services.tag_ontology import (
    OntologyParseError,
    TagAtom,
    compile_rules,
    is_valid_tag_token,
    parse_rules_text,
)


def test_parse_comments_and_blank_lines_are_ignored() -> None:
    rules = parse_rules_text(
        text="""

# comment
// comment

a => b
""",
        filename="ontology_rules.txt",
    )
    assert len(rules) == 1
    assert rules[0].rhs == "b"
    assert rules[0].lhs == (TagAtom("a"),)


def test_parse_equality_expands_to_bidirectional_implication() -> None:
    rules = parse_rules_text(text="a = b", filename="ontology_rules.txt")
    pairs = sorted((rule.lhs[0].tag, rule.rhs) for rule in rules)
    assert pairs == [("a", "b"), ("b", "a")]


def test_parse_conjunction_with_text_and_tag() -> None:
    rules = parse_rules_text(
        text='(foo "hello world") => bar',
        filename="ontology_rules.txt",
    )
    assert len(rules) == 1
    assert rules[0].rhs == "bar"
    assert len(rules[0].lhs) == 2


def test_parse_rejects_inline_comments() -> None:
    with pytest.raises(OntologyParseError) as excinfo:
        parse_rules_text(text="a => b # nope", filename="ontology_rules.txt")
    assert "inline comments" in excinfo.value.message


def test_parse_rejects_negated_tag_token() -> None:
    with pytest.raises(OntologyParseError):
        parse_rules_text(text="-foo => bar", filename="ontology_rules.txt")


def test_exact_uppercase_or_is_reserved_as_an_ontology_tag() -> None:
    assert not is_valid_tag_token("OR")
    assert is_valid_tag_token("or")

    with pytest.raises(OntologyParseError):
        parse_rules_text(text="a => OR", filename="ontology_rules.txt")


def test_inference_applies_implications_and_matchers_to_fixed_point() -> None:
    rules = parse_rules_text(
        text="""
"hello" => greeting
greeting => salutation
(greeting "world") => greeting-world
""".strip(),
        filename="ontology_rules.txt",
    )
    ontology = compile_rules(rules=rules, filename="ontology_rules.txt")

    inferred = ontology.infer_effective_tags(base_tags=frozenset(), plaintext="hello world")
    assert "greeting" in inferred
    assert "salutation" in inferred
    assert "greeting-world" in inferred


def test_quoted_text_matches_whole_words_only() -> None:
    rules = parse_rules_text(
        text='"TODO" => todo',
        filename="ontology_rules.txt",
    )
    ontology = compile_rules(rules=rules, filename="ontology_rules.txt")

    assert "todo" in ontology.infer_effective_tags(base_tags=frozenset(), plaintext="TODO")
    assert "todo" not in ontology.infer_effective_tags(base_tags=frozenset(), plaintext="TODORS")
    assert "todo" in ontology.infer_effective_tags(base_tags=frozenset(), plaintext="TODO,")


def test_quoted_text_case_heuristic_lowercase_is_case_insensitive() -> None:
    rules = parse_rules_text(
        text='"todo" => todo',
        filename="ontology_rules.txt",
    )
    ontology = compile_rules(rules=rules, filename="ontology_rules.txt")

    assert "todo" in ontology.infer_effective_tags(base_tags=frozenset(), plaintext="TODO")
    assert "todo" in ontology.infer_effective_tags(base_tags=frozenset(), plaintext="Todo")


def test_quoted_text_case_heuristic_mixed_case_is_case_sensitive() -> None:
    rules = parse_rules_text(
        text='"Todo" => todo',
        filename="ontology_rules.txt",
    )
    ontology = compile_rules(rules=rules, filename="ontology_rules.txt")

    assert "todo" in ontology.infer_effective_tags(base_tags=frozenset(), plaintext="Todo")
    assert "todo" not in ontology.infer_effective_tags(base_tags=frozenset(), plaintext="TODO")


def test_focus_view_splits_left_equals_right() -> None:
    rules = parse_rules_text(
        text="""
man => mortal
human = man
""".strip(),
        filename="ontology_rules.txt",
    )
    ontology = compile_rules(rules=rules, filename="ontology_rules.txt")

    left, equals, right = ontology.focus_view(tag="man")
    assert left == frozenset()
    assert equals == frozenset({"human", "man"})
    assert right == frozenset({"mortal"})

    left, equals, right = ontology.focus_view(tag="mortal")
    assert left == frozenset({"human", "man"})
    assert equals == frozenset({"mortal"})
    assert right == frozenset()
