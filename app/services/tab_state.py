from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Dict


class TabStateStore:
    """In-memory tab state cache keyed by the single active client."""

    _DEFAULT_TAB_ID = "0"
    _MAX_TAB_INDEX = 9

    def __init__(self) -> None:
        self._lock = Lock()
        self._active_tab_id = self._DEFAULT_TAB_ID
        self._tabs: Dict[str, Dict[str, int | str]] = {
            self._DEFAULT_TAB_ID: {"searchQuery": "", "scrollY": 0}
        }
        self._version = 0

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return self._snapshot_locked()

    def update(self, *, active_tab_id: str, tabs: Dict[str, Dict[str, object]]) -> Dict[str, object]:
        normalized_tabs = self._normalize_tabs(tabs)
        if active_tab_id not in normalized_tabs:
            raise ValueError("activeTabId must reference an existing tab")
        with self._lock:
            self._tabs = normalized_tabs
            self._active_tab_id = active_tab_id
            self._version += 1
            return self._snapshot_locked()

    def _snapshot_locked(self) -> Dict[str, object]:
        return {
            "activeTabId": self._active_tab_id,
            "tabs": deepcopy(self._tabs),
            "version": self._version,
        }

    def _normalize_tabs(self, tabs: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
        if not isinstance(tabs, dict) or not tabs:
            raise ValueError("tabs must be a non-empty object")
        normalized: Dict[str, Dict[str, object]] = {}
        for key, value in tabs.items():
            tab_id = str(key)
            if not tab_id.isdigit():
                raise ValueError("tab ids must be numeric strings")
            tab_index = int(tab_id)
            if tab_index < 0 or tab_index > self._MAX_TAB_INDEX:
                raise ValueError("tab ids must be between 0 and 9")
            if not isinstance(value, dict):
                raise ValueError("tab payload must be an object")
            if "searchQuery" not in value or "scrollY" not in value:
                raise ValueError("tab payload missing required keys")
            search_query = value["searchQuery"]
            scroll_y = value["scrollY"]
            if not isinstance(search_query, str):
                raise ValueError("searchQuery must be a string")
            if not isinstance(scroll_y, int) or scroll_y < 0:
                raise ValueError("scrollY must be a non-negative integer")
            normalized[tab_id] = {
                "searchQuery": search_query,
                "scrollY": scroll_y,
            }
        return normalized


tab_state_store = TabStateStore()
