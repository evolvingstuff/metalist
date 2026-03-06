"""In-memory UUID registry for encrypted file references."""

from __future__ import annotations

from threading import RLock


class FileRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._ids: set[str] = set()

    def reset(self) -> None:
        with self._lock:
            self._ids.clear()

    def replace_all(self, file_ids: set[str]) -> None:
        if not isinstance(file_ids, set):
            raise TypeError(f"file_ids must be a set, got {type(file_ids)}")
        for file_id in file_ids:
            if not isinstance(file_id, str) or file_id == "":
                raise TypeError("file_ids must contain non-empty strings")
        with self._lock:
            self._ids = set(file_ids)

    def add(self, file_id: str) -> None:
        if not isinstance(file_id, str) or file_id == "":
            raise TypeError("file_id must be a non-empty string")
        with self._lock:
            self._ids.add(file_id)

    def remove_many(self, file_ids: set[str]) -> None:
        if not isinstance(file_ids, set):
            raise TypeError(f"file_ids must be a set, got {type(file_ids)}")
        with self._lock:
            self._ids.difference_update(file_ids)

    def has_file(self, file_id: str) -> bool:
        if not isinstance(file_id, str) or file_id == "":
            raise TypeError("file_id must be a non-empty string")
        with self._lock:
            return file_id in self._ids

    def list_ids(self) -> set[str]:
        with self._lock:
            return set(self._ids)


file_registry = FileRegistry()
