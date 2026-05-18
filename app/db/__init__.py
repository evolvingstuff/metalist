"""DB package exports limited to schema-only to avoid import cycles.

Import DB helpers directly from `app.db.session`.
"""

from .schema import APP_SETTINGS_TABLE, LINK_TITLES_TABLE, NOTES_TABLE, initialize_schema

__all__ = [
    "APP_SETTINGS_TABLE",
    "LINK_TITLES_TABLE",
    "NOTES_TABLE",
    "initialize_schema",
]
