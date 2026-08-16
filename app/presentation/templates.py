from __future__ import annotations

from pathlib import Path
from mako.lookup import TemplateLookup


def get_templates(*, template_directory: Path) -> TemplateLookup:
    if not template_directory.is_dir():
        raise FileNotFoundError(f"Template directory not found: {template_directory}")
    return TemplateLookup(
        directories=[template_directory],
        input_encoding="utf-8",
    )
