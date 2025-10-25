from __future__ import annotations

from pathlib import Path
from typing import Optional
from mako.lookup import TemplateLookup

_lookup: Optional[TemplateLookup] = None


def get_templates() -> TemplateLookup:
    global _lookup
    if _lookup is not None:
        return _lookup

    app_dir = Path(__file__).resolve().parent.parent
    _lookup = TemplateLookup(
        directories=[app_dir / "templates"],
        module_directory=str(app_dir / "__pycache__" / "mako_modules"),
        input_encoding="utf-8",
    )
    return _lookup

