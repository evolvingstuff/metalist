from app.services.tag_rename import rename_tag_in_tag_bar


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

