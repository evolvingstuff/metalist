"""Memory mode backend helpers.

Provides in-memory tracking of note feedback and selection utilities
for the spaced-repetition style memory feature.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from threading import Lock
from typing import Dict, Iterable, List, Tuple

from sqlalchemy.orm import Session

from ..models.linked_list import LinkedListManager
from ..render.note_renderer import build_note_tree


@dataclass(frozen=True)
class MemoryStats:
    score: float
    count: int

    @property
    def average(self) -> float:
        if self.count == 0:
            return 0.0
        return self.score / self.count


class _MemoryTracker:
    """Thread-safe in-memory store for note feedback aggregates."""

    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, int]] = {}
        self._lock = Lock()

    def record(self, note_id: str, outcome: int) -> MemoryStats:
        if outcome not in (-1, 0, 1):
            raise ValueError(f"Invalid outcome {outcome}; expected -1, 0, or 1")

        with self._lock:
            total, count = self._data.get(note_id, (0.0, 0))
            total += float(outcome)
            count += 1
            self._data[note_id] = (total, count)
            return MemoryStats(score=total, count=count)

    def get(self, note_id: str) -> MemoryStats:
        with self._lock:
            total, count = self._data.get(note_id, (0.0, 0))
            return MemoryStats(score=total, count=count)

    def bulk_stats(self, note_ids: Iterable[str]) -> Dict[str, MemoryStats]:
        with self._lock:
            return {
                note_id: MemoryStats(*self._data.get(note_id, (0.0, 0)))
                for note_id in note_ids
            }


_tracker = _MemoryTracker()


class MemoryService:
    """High-level helper for memory mode operations."""

    def __init__(self, db: Session, temperature: float = 0.25) -> None:
        if temperature <= 0:
            raise ValueError("Temperature must be positive for softmax weighting")
        self.db = db
        self.temperature = temperature

    def record_feedback(self, note_id: str, outcome: int) -> MemoryStats:
        return _tracker.record(note_id, outcome)

    def get_stats(self, note_id: str) -> MemoryStats:
        return _tracker.get(note_id)

    def build_candidate_tree(self, search_query: str | None = None) -> List[dict]:
        """Return the rendered note tree for the current search context."""
        return build_note_tree(LinkedListManager, self.db, None, None, search_query)

    def choose_note(self, notes: List[dict]) -> Tuple[dict, dict, MemoryStats, float]:
        """Select a note using softmax-weighted probabilities.

        Returns a tuple of (selected_note_dict, root_note_dict, stats, probability).
        """
        if not notes:
            raise ValueError("Cannot choose note from an empty note list")

        flattened: List[Tuple[dict, dict]] = []

        def _walk(node: dict, root: dict) -> None:
            flattened.append((node, root))
            for child in node.get('children', []):
                _walk(child, root)

        for root_note in notes:
            _walk(root_note, root_note)

        if not flattened:
            raise ValueError("No candidate notes available after producing flattened list")

        note_ids = [node['id'] for node, _ in flattened]
        stats_map = _tracker.bulk_stats(note_ids)

        scores = [stats_map[note_id].average for note_id in note_ids]
        max_score = max(scores)

        scaled = [math.exp((score - max_score) / self.temperature) for score in scores]
        weight_sum = sum(scaled)
        if weight_sum == 0:
            raise RuntimeError("Softmax weighting produced zero total weight")

        population = [pair for pair in flattened]
        chosen_index = random.choices(range(len(population)), weights=scaled, k=1)[0]
        selected_node, root_node = population[chosen_index]
        selected_id = selected_node['id']
        selected_stats = stats_map[selected_id]
        probability = scaled[chosen_index] / weight_sum

        return selected_node, root_node, selected_stats, probability


def apply_memory_flags(root_node: dict, selected_id: str) -> None:
    """Highlight the selected node for memory mode."""
    def _apply(node: dict) -> None:
        flags = node.setdefault('flags', {})
        flags['memoryMode'] = True
        if node['id'] == selected_id:
            flags['memorySelected'] = True
        else:
            flags.pop('memorySelected', None)
        for child in node.get('children', []):
            _apply(child)

    _apply(root_node)


__all__ = [
    'MemoryService',
    'MemoryStats',
    'apply_memory_flags',
]
