from __future__ import annotations

from pathlib import Path
from mako.lookup import TemplateLookup


def get_templates(*, template_directory: Path, module_directory: Path) -> TemplateLookup:
    if not template_directory.is_dir():
        raise FileNotFoundError(f"Template directory not found: {template_directory}")
    if not module_directory.is_dir():
        raise FileNotFoundError(f"Template module directory not found: {module_directory}")
    return TemplateLookup(
        directories=[template_directory],
        module_directory=str(module_directory),
        input_encoding="utf-8",
    )
