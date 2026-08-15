from __future__ import annotations

from pathlib import Path

import pytest

from app.models.database import SafeSession
from app.security.encryption import set_encryption_required
from app.services.tab_state import TabStateStore


@pytest.fixture(autouse=True)
def _isolated_memory_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        yield
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_create_tab_copies_sort_mode_from_source_tab() -> None:
    store = TabStateStore()
    initial = store.snapshot()
    source_tab_id = initial["activeTabId"]
    initial["tabs"][source_tab_id]["sortMode"] = "updated"
    initial["tabs"][source_tab_id]["calendarMetric"] = "updated"
    initial["tabs"][source_tab_id]["calendarScrollTop"] = 420
    initial["tabs"][source_tab_id]["calendarScrollPinnedToNewest"] = False
    updated = store.update(
        active_tab_id=source_tab_id,
        tabs=initial["tabs"],
        tab_order=initial["tabOrder"],
    )

    duplicated = store.create_tab(copy_from_tab_id=source_tab_id)
    new_tab_id = duplicated["newTabId"]

    assert duplicated["tabs"][new_tab_id]["sortMode"] == "updated"
    assert duplicated["tabs"][new_tab_id]["calendarMetric"] == "updated"
    assert duplicated["tabs"][new_tab_id]["calendarScrollTop"] == 420
    assert duplicated["tabs"][new_tab_id]["calendarScrollPinnedToNewest"] is False
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


def test_set_sort_mode_accepts_alphabetical() -> None:
    store = TabStateStore()
    snapshot = store.snapshot()
    tab_id = snapshot["activeTabId"]

    result = store.set_sort_mode(tab_id=tab_id, sort_mode="alphabetical")

    assert result["changed"] is True
    assert result["tabs"][tab_id]["sortMode"] == "alphabetical"


def test_set_sort_mode_accepts_content_volume() -> None:
    store = TabStateStore()
    snapshot = store.snapshot()
    tab_id = snapshot["activeTabId"]

    result = store.set_sort_mode(tab_id=tab_id, sort_mode="content-volume")

    assert result["changed"] is True
    assert result["tabs"][tab_id]["sortMode"] == "content-volume"


def test_set_date_filter_resets_scroll_state_and_marks_change() -> None:
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

    result = store.set_date_filter(
        tab_id=tab_id,
        date_filter={"metric": "updated", "startDate": "2026-05-12", "endDate": "2026-05-18"},
    )

    assert result["changed"] is True
    assert result["tabs"][tab_id]["dateFilter"] == {
        "metric": "updated",
        "startDate": "2026-05-12",
        "endDate": "2026-05-18",
    }
    assert result["tabs"][tab_id]["scrollY"] == 0
    assert result["tabs"][tab_id]["scrollAnchor"] is None


def test_set_date_filter_rejects_missing_range_field() -> None:
    store = TabStateStore()
    snapshot = store.snapshot()
    tab_id = snapshot["activeTabId"]

    with pytest.raises(ValueError, match="exactly"):
        store.set_date_filter(
            tab_id=tab_id,
            date_filter={"metric": "updated", "startDate": "2026-05-12"},
        )


def test_bootstrap_restores_persisted_tab_state(
) -> None:
    store = TabStateStore()
    initial = store.snapshot()
    tab_id = initial["activeTabId"]
    payload = initial["tabs"]
    payload[tab_id]["searchQuery"] = "project-x"
    payload[tab_id]["scrollY"] = 180
    payload[tab_id]["anchorRootId"] = "root-1"
    payload[tab_id]["scrollAnchor"] = {
        "anchorId": "root-1",
        "anchorBias": "top",
        "intraOffset": 12,
        "beltPrev": ["root-0"],
        "beltNext": ["root-2"],
        "anchorSortKey": {"domIndex": 3},
    }
    payload[tab_id]["dateFilter"] = {
        "metric": "created",
        "startDate": "2026-05-01",
        "endDate": "2026-05-18",
    }
    payload[tab_id]["calendarMetric"] = "created"
    payload[tab_id]["calendarScrollTop"] = 333
    payload[tab_id]["calendarScrollPinnedToNewest"] = False
    persisted = store.update(
        active_tab_id=tab_id,
        tabs=payload,
        tab_order=initial["tabOrder"],
    )

    reloaded = TabStateStore()
    session = SafeSession()
    try:
        with SafeSession.allow_reads("tests:tab_state:bootstrap"):
            reloaded.bootstrap(connection=session.connection())
    finally:
        session.close()

    snapshot = reloaded.snapshot()
    assert snapshot == persisted
    assert snapshot["tabs"][tab_id]["searchQuery"] == "project-x"
    assert snapshot["tabs"][tab_id]["anchorRootId"] == "root-1"
    assert snapshot["tabs"][tab_id]["dateFilter"]["metric"] == "created"
    assert snapshot["tabs"][tab_id]["calendarMetric"] == "created"
    assert snapshot["tabs"][tab_id]["calendarScrollTop"] == 333
    assert snapshot["tabs"][tab_id]["calendarScrollPinnedToNewest"] is False


def test_legacy_tab_payload_defaults_calendar_state() -> None:
    store = TabStateStore()
    initial = store.snapshot()
    tab_id = initial["activeTabId"]
    payload = initial["tabs"]
    del payload[tab_id]["calendarMetric"]
    del payload[tab_id]["calendarScrollTop"]
    del payload[tab_id]["calendarScrollPinnedToNewest"]

    updated = store.update(
        active_tab_id=tab_id,
        tabs=payload,
        tab_order=initial["tabOrder"],
    )

    assert updated["tabs"][tab_id]["calendarMetric"] == "created"
    assert updated["tabs"][tab_id]["calendarScrollTop"] == 0
    assert updated["tabs"][tab_id]["calendarScrollPinnedToNewest"] is True
