"""Deprecated: memory routes moved to app/api/routes/memory.py.

This module remains to avoid breaking imports. For memory logic, use
app.services.memory_service.
"""

from .memory_service import MemoryService  # re-export service symbol

__all__ = ["MemoryService"]
