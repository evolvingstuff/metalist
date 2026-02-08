import pytest

from app.services.tag_rename import rename_tag_in_tag_bar, toggle_meta_tag_pair_in_tag_bar


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
