from __future__ import annotations

from copy import deepcopy
import re
from threading import Lock
from typing import Dict, List, Optional
from uuid import uuid4


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def _is_uuid_string(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if not value:
        return False
    if _UUID_RE.match(value) is None:
        return False
    return True


class TabStateStore:
    """In-memory tab state cache keyed by the single active client."""

    _MAX_TABS = 10

    def __init__(self) -> None:
        default_tab_id = self._new_tab_id()
        self._lock = Lock()
        self._active_tab_id = default_tab_id
        self._tabs: Dict[str, Dict[str, object]] = {
            default_tab_id: {"searchQuery": "", "scrollY": 0, "scrollAnchor": None}
        }
        self._tab_order = [default_tab_id]
        self._version = 0

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return self._snapshot_locked()

    def create_tab(self, *, copy_from_tab_id: str) -> Dict[str, object]:
        if not isinstance(copy_from_tab_id, str) or not copy_from_tab_id:
            raise ValueError("copyFromTabId must be a non-empty string")
        if not _is_uuid_string(copy_from_tab_id):
            raise ValueError("copyFromTabId must be a UUID string")

        with self._lock:
            if copy_from_tab_id not in self._tabs:
                raise ValueError("copyFromTabId must reference an existing tab")
            if len(self._tabs) >= self._MAX_TABS:
                raise ValueError(f"max tabs reached ({self._MAX_TABS})")

            new_tab_id = self._new_tab_id()
            while new_tab_id in self._tabs:
                new_tab_id = self._new_tab_id()

            source = deepcopy(self._tabs[copy_from_tab_id])
            self._tabs[new_tab_id] = source
            self._tab_order.append(new_tab_id)
            self._version += 1
            snapshot = self._snapshot_locked()
            snapshot["newTabId"] = new_tab_id
            return snapshot

    def delete_tab(self, *, tab_id: str) -> Dict[str, object]:
        if not isinstance(tab_id, str) or not tab_id:
            raise ValueError("tabId must be a non-empty string")
        if not _is_uuid_string(tab_id):
            raise ValueError("tabId must be a UUID string")

        with self._lock:
            if tab_id not in self._tabs:
                raise ValueError("tabId must reference an existing tab")
            if len(self._tabs) <= 1:
                raise ValueError("cannot delete the last remaining tab")

            was_active = tab_id == self._active_tab_id
            order = list(self._tab_order)
            idx = order.index(tab_id)
            order.pop(idx)
            del self._tabs[tab_id]

            if was_active:
                if idx < len(order):
                    next_active = order[idx]
                else:
                    next_active = order[idx - 1]
                self._active_tab_id = next_active

            self._tab_order = order
            self._version += 1
            return self._snapshot_locked()

    def update(
        self,
        *,
        active_tab_id: str,
        tabs: Dict[str, Dict[str, object]],
        tab_order: List[str],
    ) -> Dict[str, object]:
        normalized_tabs = self._normalize_tabs(tabs)
        normalized_order = self._normalize_tab_order(tab_order, normalized_tabs)
        if active_tab_id not in normalized_tabs:
            raise ValueError("activeTabId must reference an existing tab")
        with self._lock:
            existing_ids = set(self._tabs.keys())
            incoming_ids = set(normalized_tabs.keys())
            if incoming_ids != existing_ids:
                raise ValueError("tab ids mismatch; use tab-state new/delete endpoints")
            self._tabs = normalized_tabs
            self._active_tab_id = active_tab_id
            self._tab_order = normalized_order
            self._version += 1
            return self._snapshot_locked()

    def _snapshot_locked(self) -> Dict[str, object]:
        return {
            "activeTabId": self._active_tab_id,
            "tabs": deepcopy(self._tabs),
            "tabOrder": list(self._tab_order),
            "version": self._version,
        }

    def _new_tab_id(self) -> str:
        # Version-4 UUID; validated by the normalize path.
        return str(uuid4())

    def _normalize_tab_order(self, incoming_order: List[str], tabs: Dict[str, Dict[str, object]]) -> List[str]:
        if not incoming_order:
            raise ValueError("tabOrder must be a non-empty list")
        if len(incoming_order) != len(tabs):
            raise ValueError("tabOrder must match tabs length")
        if len(incoming_order) > self._MAX_TABS:
            raise ValueError(f"tabOrder exceeds max tabs ({self._MAX_TABS})")

        normalized: List[str] = []
        seen = set()
        for raw in incoming_order:
            tab_id = str(raw)
            if tab_id in seen:
                raise ValueError("tabOrder contains duplicates")
            if tab_id not in tabs:
                raise ValueError("tabOrder references unknown tab")
            seen.add(tab_id)
            normalized.append(tab_id)
        return normalized

    def _normalize_tabs(self, tabs: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
        if not isinstance(tabs, dict) or not tabs:
            raise ValueError("tabs must be a non-empty object")
        if len(tabs) > self._MAX_TABS:
            raise ValueError(f"tabs must contain at most {self._MAX_TABS} entries")
        normalized: Dict[str, Dict[str, object]] = {}
        for key, value in tabs.items():
            tab_id = str(key)
            if not tab_id:
                raise ValueError("tab ids must be non-empty strings")
            if not _is_uuid_string(tab_id):
                raise ValueError("tab ids must be UUID strings")
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

            scroll_anchor = value["scrollAnchor"]
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
