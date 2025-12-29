from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Dict, List, Optional


class TabStateStore:
    """In-memory tab state cache keyed by the single active client."""

    _DEFAULT_TAB_ID = "0"
    _MAX_TAB_INDEX = 9

    def __init__(self) -> None:
        self._lock = Lock()
        self._active_tab_id = self._DEFAULT_TAB_ID
        self._tabs: Dict[str, Dict[str, object]] = {
            self._DEFAULT_TAB_ID: {"searchQuery": "", "scrollY": 0, "scrollAnchor": None}
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

            scroll_anchor = value.get("scrollAnchor")
            normalized_scroll_anchor: Optional[Dict[str, object]] = None
            if scroll_anchor is not None:
                if not isinstance(scroll_anchor, dict):
                    raise ValueError("scrollAnchor must be an object or null")

                anchor_id = scroll_anchor.get("anchorId")
                anchor_bias = scroll_anchor.get("anchorBias")
                intra_offset = scroll_anchor.get("intraOffset")
                belt_prev = scroll_anchor.get("beltPrev")
                belt_next = scroll_anchor.get("beltNext")
                anchor_sort_key = scroll_anchor.get("anchorSortKey")

                if not isinstance(anchor_id, str) or not anchor_id:
                    raise ValueError("scrollAnchor.anchorId must be a non-empty string")
                if anchor_bias not in ("center", "top"):
                    raise ValueError("scrollAnchor.anchorBias must be 'center' or 'top'")
                if not isinstance(intra_offset, int) or intra_offset < 0:
                    raise ValueError("scrollAnchor.intraOffset must be a non-negative integer")
                if not isinstance(belt_prev, list) or not isinstance(belt_next, list):
                    raise ValueError("scrollAnchor belt arrays must be lists")

                def _normalize_belt(payload: List[object]) -> List[str]:
                    return [entry for entry in payload if isinstance(entry, str) and entry]

                normalized_prev = _normalize_belt(belt_prev)
                normalized_next = _normalize_belt(belt_next)

                if not isinstance(anchor_sort_key, dict):
                    raise ValueError("scrollAnchor.anchorSortKey must be an object")
                dom_index = anchor_sort_key.get("domIndex")
                if not isinstance(dom_index, int) or dom_index < 0:
                    raise ValueError("scrollAnchor.anchorSortKey.domIndex must be a non-negative integer")

                normalized_scroll_anchor = {
                    "anchorId": anchor_id,
                    "anchorBias": anchor_bias,
                    "intraOffset": intra_offset,
                    "beltPrev": normalized_prev,
                    "beltNext": normalized_next,
                    "anchorSortKey": {"domIndex": dom_index},
                }
            normalized[tab_id] = {
                "searchQuery": search_query,
                "scrollY": scroll_y,
                "scrollAnchor": normalized_scroll_anchor,
            }
        return normalized


tab_state_store = TabStateStore()
