"""Memory mode backend helpers.

Provides in-memory tracking of note feedback and selection utilities
for the spaced-repetition style memory feature.
"""

from __future__ import annotations

import random
from threading import Lock
from typing import Dict, Iterable, List, Tuple

from ..models.linked_list import LinkedListManager
from app.presentation.render.note_renderer import build_note_tree
from ..models.database import SafeSession


class MemoryStats:
    __slots__ = ('pos', 'neg')

    def __init__(self, pos: float, neg: float) -> None:
        if pos < 0:
            raise ValueError('pos cannot be negative')
        if neg < 0:
            raise ValueError('neg cannot be negative')
        self.pos = pos
        self.neg = neg

    @property
    def total(self) -> float:
        return self.pos + self.neg

    @property
    def ratio(self) -> float:
        # Symmetric Laplace smoothing keeps a neutral baseline while rewarding extra positives.
        smoothed_pos = self.pos + 1.0
        smoothed_neg = self.neg + 1.0
        smoothed_total = smoothed_pos + smoothed_neg
        assert smoothed_total > 0.0
        return smoothed_pos / smoothed_total

    def as_tuple(self) -> Tuple[float, float]:
        return self.pos, self.neg


class _MemoryTracker:
    """Thread-safe in-memory store for Laplace-smoothed note feedback."""

    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, float]] = {}
        self._lock = Lock()

    def record(self, note_id: str, outcome: int) -> MemoryStats:
        if outcome not in (-1, 0, 1):
            raise ValueError(f"Invalid outcome {outcome}; expected -1, 0, or 1")

        with self._lock:
            pos, neg = self._data.get(note_id, (0.0, 0.0))
            if outcome == 1:
                pos += 1.0
            elif outcome == -1:
                neg += 1.0
            self._data[note_id] = (pos, neg)
            return MemoryStats(pos, neg)

    def get(self, note_id: str) -> MemoryStats:
        with self._lock:
            pos, neg = self._data.get(note_id, (0.0, 0.0))
            return MemoryStats(pos, neg)

    def bulk_stats(self, note_ids: Iterable[str]) -> Dict[str, MemoryStats]:
        with self._lock:
            return {
                note_id: MemoryStats(*self._data.get(note_id, (0.0, 0.0)))
                for note_id in note_ids
            }


_tracker = _MemoryTracker()


class MemoryService:
    """High-level helper for memory mode operations."""

    def __init__(self, db: SafeSession) -> None:
        self.db = db

    def record_feedback(self, note_id: str, outcome: int) -> MemoryStats:
        return _tracker.record(note_id, outcome)

    def get_stats(self, note_id: str) -> MemoryStats:
        return _tracker.get(note_id)

    def build_candidate_tree(self, search_query: str | None = None) -> List[dict]:
        """Return the rendered note tree for the current search context."""
        return build_note_tree(LinkedListManager, self.db, None, None, search_query)

    def choose_note(
        self,
        notes: List[dict],
        previous_note_id: str | None = None,
    ) -> Tuple[dict, dict, MemoryStats, float]:
        """Select the note with the strongest positive feedback ratio.

        Returns (selected_note_dict, root_note_dict, stats, ratio).
        """
        if not notes:
            raise ValueError("Cannot choose note from an empty note list")

        flattened: List[Tuple[dict, dict]] = []

        def _walk(node: dict, root: dict) -> None:
            flattened.append((node, root))
            for child in node['children']:
                _walk(child, root)

        for root_note in notes:
            _walk(root_note, root_note)

        if not flattened:
            raise ValueError("No candidate notes available after producing flattened list")

        note_ids = [node['id'] for node, _ in flattened]
        stats_map = _tracker.bulk_stats(note_ids)

        if previous_note_id and len(flattened) > 1:
            filtered = [
                (node, root) for node, root in flattened if node['id'] != previous_note_id
            ]
            if filtered:
                flattened = filtered

        weights: List[float] = []
        for node, _ in flattened:
            weights.append(stats_map[node['id']].ratio)

        total_weight = sum(weights)
        if total_weight <= 0:
            raise RuntimeError("Failed to compute positive selection weights")

        normalized_total = sum(weight / total_weight for weight in weights)
        if abs(1.0 - normalized_total) > 1e-6:
            raise RuntimeError(
                f"Memory selection weights corrupted: normalized total {normalized_total} != 1.0"
            )

        target = random.random() * total_weight
        cumulative = 0.0
        chosen_index = None

        for idx, weight in enumerate(weights):
            cumulative += weight
            if target <= cumulative:
                chosen_index = idx
                break

        if chosen_index is None:
            chosen_index = len(flattened) - 1

        selected_node, root_node = flattened[chosen_index]
        selected_stats = stats_map[selected_node['id']]
        probability = weights[chosen_index] / total_weight

        return selected_node, root_node, selected_stats, probability


def apply_memory_flags(root_node: dict, selected_id: str) -> None:
    """Highlight selection and collapse branches outside the selected subtree."""

    def _apply(node: dict, within_selected: bool = False) -> bool:
        flags = node.setdefault('flags', {})
        flags['memoryMode'] = True

        is_selected = node['id'] == selected_id
        contains_selected = is_selected

        for child in node['children']:
            if _apply(child, within_selected or is_selected):
                contains_selected = True

        if is_selected:
            flags['memorySelected'] = True
        else:
            flags.pop('memorySelected', None)

        is_in_selected_path = contains_selected or within_selected
        if is_in_selected_path:
            flags['isCollapsed'] = False
        else:
            flags['isCollapsed'] = True

        return contains_selected or within_selected

    _apply(root_node)


__all__ = [
    'MemoryService',
    'MemoryStats',
    'apply_memory_flags',
]
