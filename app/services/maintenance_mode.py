"""Maintenance mode service for bulk operations."""

import threading
from typing import Optional


class MaintenanceModeService:
    """Service for managing maintenance mode during bulk operations."""
    
    def __init__(self):
        self._maintenance_active = False
        self._operation_description = ""
        self._lock = threading.Lock()
    
    def enter_maintenance(self, operation_description: str = "Processing") -> None:
        """Enter maintenance mode with optional description.
        
        Args:
            operation_description: Description of the operation in progress
        """
        with self._lock:
            self._maintenance_active = True
            self._operation_description = operation_description
            print(f"[MaintenanceMode] Entered maintenance mode: {operation_description}")
    
    def exit_maintenance(self) -> None:
        """Exit maintenance mode."""
        with self._lock:
            operation = self._operation_description
            self._maintenance_active = False
            self._operation_description = ""
            print(f"[MaintenanceMode] Exited maintenance mode: {operation}")
    
    def is_active(self) -> bool:
        """Check if maintenance mode is currently active."""
        with self._lock:
            return self._maintenance_active
    
    def get_operation_description(self) -> str:
        """Get current operation description."""
        with self._lock:
            return self._operation_description


# Global maintenance mode service instance
maintenance_service = MaintenanceModeService()