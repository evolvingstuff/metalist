from __future__ import annotations

from app.services.tab_state import TabStateStore


def test_create_tab_copies_sort_mode_from_source_tab() -> None:
    store = TabStateStore()
    initial = store.snapshot()
    source_tab_id = initial["activeTabId"]
    initial["tabs"][source_tab_id]["sortMode"] = "updated"
    updated = store.update(
        active_tab_id=source_tab_id,
        tabs=initial["tabs"],
        tab_order=initial["tabOrder"],
    )

    duplicated = store.create_tab(copy_from_tab_id=source_tab_id)
    new_tab_id = duplicated["newTabId"]

    assert duplicated["tabs"][new_tab_id]["sortMode"] == "updated"
    assert updated["tabs"][source_tab_id]["sortMode"] == "updated"


def test_set_sort_mode_resets_scroll_state_and_marks_change() -> None:
    store = TabStateStore()
    snapshot = store.snapshot()
    tab_id = snapshot["activeTabId"]
    payload = snapshot["tabs"]
    payload[tab_id]["scrollY"] = 250
    payload[tab_id]["scrollAnchor"] = {
        "anchorId": "root-a",
        "anchorBias": "top",
        "intraOffset": 0,
        "beltPrev": [],
        "beltNext": [],
        "anchorSortKey": {"domIndex": 0},
    }
    store.update(
        active_tab_id=tab_id,
        tabs=payload,
        tab_order=snapshot["tabOrder"],
    )

    result = store.set_sort_mode(tab_id=tab_id, sort_mode="created")

    assert result["changed"] is True
    assert result["tabs"][tab_id]["sortMode"] == "created"
    assert result["tabs"][tab_id]["scrollY"] == 0
    assert result["tabs"][tab_id]["scrollAnchor"] is None


def test_set_sort_mode_is_noop_when_value_matches() -> None:
    store = TabStateStore()
    snapshot = store.snapshot()
    tab_id = snapshot["activeTabId"]

    result = store.set_sort_mode(tab_id=tab_id, sort_mode="normal")

    assert result["changed"] is False
    assert result["tabs"][tab_id]["sortMode"] == "normal"
