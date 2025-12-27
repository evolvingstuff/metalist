from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ViewState:
    """Represents the visible portion of the note tree for a specific tab/view."""

    structure: List[Dict[str, object]]
    payloads: Dict[str, Dict[str, object]]
    locks: Dict[str, str]
    children_by_parent: Dict[Optional[str], List[str]]
    hash_by_id: Dict[str, str]
    metadata: Dict[str, object] = field(default_factory=dict)

    def visible_note_ids(self) -> List[str]:
        return list(self.hash_by_id.keys())
