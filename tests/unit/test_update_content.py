from __future__ import annotations

import app.usecases.update_content as update_content_module


def test_record_added_tag_activity_records_new_non_meta_tags(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def _record_search_interaction(*, query: str, interaction_type: str, token: str) -> bool:
        calls.append((query, interaction_type, token))
        return True

    monkeypatch.setattr(
        update_content_module,
        "record_search_interaction",
        _record_search_interaction,
    )

    update_content_module._record_added_tag_activity(
        before_tags="scratchpad Existing",
        after_tags="scratchpad existing @done new-tag another",
        token="token",
    )

    assert calls == [
        ("another", "tag", "token"),
        ("new-tag", "tag", "token"),
    ]
