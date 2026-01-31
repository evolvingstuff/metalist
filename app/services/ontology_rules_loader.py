from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.services.tag_ontology import TagOntology, compile_rules, parse_rules_text


_CACHED: Optional[TagOntology] = None


def load_ontology_rules() -> TagOntology:
    """Load ontology rules from `ontology_rules.txt` at repo root.

    This is Phase-1 scaffolding; edits require a server restart.
    """

    global _CACHED
    if _CACHED is not None:
        return _CACHED

    rules_path = Path(__file__).resolve().parents[2] / "ontology_rules.txt"
    if not rules_path.exists():
        _CACHED = TagOntology.empty()
        return _CACHED

    text = rules_path.read_text(encoding="utf-8")
    parsed = parse_rules_text(text=text, filename=str(rules_path))
    _CACHED = compile_rules(rules=parsed, filename=str(rules_path))
    return _CACHED

