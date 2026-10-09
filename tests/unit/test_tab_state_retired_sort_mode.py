"""Saved tab state only keeps sort modes this version knows (reported login failure).

A removed similar-notes view had saved "similarity:<note id>" as a tab's sort
mode; loading it stopped login. Saved values outside the known modes now open in
normal order; requests from the browser still fail on an unknown mode.
"""

from __future__ import annotations

import json

import pytest

from app.services.tab_state import TabStateStore, _normalize_tab_sort_mode


def test_unknown_saved_sort_modes_open_in_normal_order() -> None:
    for saved in ("similarity:155064fb-7833-45a7-81ff-74b8cc77110f", "by-magic", "", 7, None):
        assert _normalize_tab_sort_mode(saved, from_storage=True) == "normal"
    assert _normalize_tab_sort_mode("Created", from_storage=True) == "created"


def test_requests_with_an_unknown_sort_mode_still_fail() -> None:
    assert _normalize_tab_sort_mode("updated", from_storage=False) == "updated"
    with pytest.raises(ValueError):
        _normalize_tab_sort_mode("similarity:155064fb-7833-45a7-81ff-74b8cc77110f", from_storage=False)


def test_a_saved_tab_from_the_removed_view_loads_in_normal_order() -> None:

    tab_id = "6f0a1c2e-1111-4222-8333-444455556666"
    other_id = "6f0a1c2e-1111-4222-8333-777788889999"
    snapshot = TabStateStore()._deserialize_snapshot_json(json.dumps({
        "activeTabId": tab_id,
        "tabOrder": [other_id, tab_id],
        "version": 3,
        "tabs": {
            other_id: {"searchQuery": "project", "scrollY": 0, "anchorRootId": None, "scrollAnchor": None,
                       "sortMode": "created"},
            tab_id: {"searchQuery": "id-1 OR id-2", "scrollY": 0, "anchorRootId": None, "scrollAnchor": None,
                     "sortMode": "similarity:155064fb-7833-45a7-81ff-74b8cc77110f"},
        },
    }))
    assert snapshot["tabs"][tab_id]["sortMode"] == "normal"
    assert snapshot["tabs"][other_id]["sortMode"] == "created"
