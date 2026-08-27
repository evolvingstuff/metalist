import pytest

from app.services.tag_rename import (
    delete_tag_from_tag_bar,
    rename_tag_in_tag_bar,
    toggle_meta_tag_pair_in_tag_bar,
)


def test_delete_tag_from_tag_bar_removes_bare_and_wrapped_tokens() -> None:
    tags = "foo alpha [foo beta] {gamma foo} (foo)"
    updated, changed = delete_tag_from_tag_bar(tags=tags, tag="foo")
    assert changed is True
    assert updated == " alpha [beta] {gamma} "


def test_delete_tag_from_tag_bar_ignores_block_comments_and_partial_matches() -> None:
    tags = "foo foobar /* foo */ barfoo"
    updated, changed = delete_tag_from_tag_bar(tags=tags, tag="foo")
    assert changed is True
    assert updated == " foobar /* foo */ barfoo"


def test_delete_tag_from_tag_bar_reports_unchanged_when_tag_is_absent() -> None:
    tags = "alpha beta"
    updated, changed = delete_tag_from_tag_bar(tags=tags, tag="foo")
    assert changed is False
    assert updated == tags


def test_rename_tag_in_tag_bar_bare_tokens_preserves_whitespace() -> None:
    tags = "  alpha  beta\told  "
    updated, changed = rename_tag_in_tag_bar(tags=tags, old="old", new="new")
    assert changed is True
    assert updated == "  alpha  beta\tnew  "


def test_rename_tag_in_tag_bar_ignores_block_comments() -> None:
    tags = "old /* old should stay */ old"
    updated, changed = rename_tag_in_tag_bar(tags=tags, old="old", new="new")
    assert changed is True
    assert updated == "new /* old should stay */ new"


def test_rename_tag_in_tag_bar_rewrites_wrapped_tokens() -> None:
    tags = "[old other] {keep old}"
    updated, changed = rename_tag_in_tag_bar(tags=tags, old="old", new="new")
    assert changed is True
    assert updated == "[new other] {keep new}"


def test_toggle_meta_tag_pair_in_tag_bar_swaps_todo_done() -> None:
    tags = "@todo alpha"
    updated, changed = toggle_meta_tag_pair_in_tag_bar(tags=tags, tag_a="@todo", tag_b="@done")
    assert changed is True
    assert updated == "@done alpha"


def test_toggle_meta_tag_pair_in_tag_bar_swaps_done_todo() -> None:
    tags = "@done alpha"
    updated, changed = toggle_meta_tag_pair_in_tag_bar(tags=tags, tag_a="@todo", tag_b="@done")
    assert changed is True
    assert updated == "@todo alpha"


def test_toggle_meta_tag_pair_in_tag_bar_preserves_wrapped_tokens() -> None:
    tags = "[@todo] @todo"
    updated, changed = toggle_meta_tag_pair_in_tag_bar(tags=tags, tag_a="@todo", tag_b="@done")
    assert changed is True
    assert updated == "[@todo] @done"


def test_toggle_meta_tag_pair_in_tag_bar_ignores_comments() -> None:
    tags = "@todo /* @todo */"
    updated, changed = toggle_meta_tag_pair_in_tag_bar(tags=tags, tag_a="@todo", tag_b="@done")
    assert changed is True
    assert updated == "@done /* @todo */"


def test_toggle_meta_tag_pair_in_tag_bar_raises_on_conflict() -> None:
    tags = "@todo @done"
    with pytest.raises(RuntimeError):
        toggle_meta_tag_pair_in_tag_bar(tags=tags, tag_a="@todo", tag_b="@done")
