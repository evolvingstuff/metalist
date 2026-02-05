#!/usr/bin/env python3
"""Import legacy MetaList JSON exports into the current SQLite schema.

This script deletes the existing SQLite database referenced by
`app.config.DATABASE_URL`, recreates the schema, and imports notes from the
legacy JSON format. Use with care: this is destructive.
"""

from __future__ import annotations

import argparse
import json
import sys
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception as exc:  # External dependency may be missing in headless envs.
    tk = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]
    _TK_IMPORT_ERROR = exc
else:
    _TK_IMPORT_ERROR = None

from app.config import DATABASE_URL
from app.db.notes_sql import insert_note, update_links
from app.db.ontology_rules_sql import insert_rule
from app.db.settings_sql import insert_default_settings
from app.models.database import SafeSession
from app.utils.text_utils import strip_html


@dataclass(frozen=True)
class NoteMeta:
    parent_id: str | None
    is_collapsed: bool
    updated_at: datetime


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert legacy MetaList JSON exports into the current SQLite schema.",
    )
    parser.add_argument(
        "--input",
        dest="input_path",
        help="Path to the legacy JSON export. If omitted, a file picker opens.",
    )
    return parser.parse_args(argv)


def _resolve_sqlite_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError(f"Unsupported DATABASE_URL: {database_url}")
    raw_path = database_url.replace("sqlite:///", "", 1)
    path = Path(raw_path)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _delete_existing_db(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    wal_path = db_path.with_name(f"{db_path.name}-wal")
    if wal_path.exists():
        wal_path.unlink()
    shm_path = db_path.with_name(f"{db_path.name}-shm")
    if shm_path.exists():
        shm_path.unlink()


def _pick_input_path() -> Path:
    if tk is None or filedialog is None:
        raise RuntimeError(
            f"tkinter is unavailable for the file picker ({_TK_IMPORT_ERROR}). "
            "Run again with --input /path/to/export.json."
        )
    try:
        root = tk.Tk()
    except Exception as exc:
        raise RuntimeError(
            "Unable to open the file picker. "
            "Run again with --input /path/to/export.json."
        ) from exc
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="Select legacy MetaList export (JSON)",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
    finally:
        root.destroy()
    if not selected:
        raise RuntimeError("No file selected. Provide --input to specify the file path.")
    return Path(selected)


def _resolve_input_path(input_path: str | None) -> Path:
    if input_path is None:
        path = _pick_input_path()
    else:
        path = Path(input_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Legacy export not found: {path}")
    if not path.is_file():
        raise RuntimeError(f"Legacy export is not a file: {path}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise TypeError("Legacy export must be a JSON object.")
    return payload


def _require_dict(obj: dict[str, Any], key: str) -> dict[str, Any]:
    if key not in obj:
        raise KeyError(f"Missing required field: {key}")
    value = obj[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object.")
    return value


def _require_list(obj: dict[str, Any], key: str) -> list[Any]:
    if key not in obj:
        raise KeyError(f"Missing required field: {key}")
    value = obj[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list.")
    return value


def _require_int(obj: dict[str, Any], key: str) -> int:
    if key not in obj:
        raise KeyError(f"Missing required field: {key}")
    value = obj[key]
    if not isinstance(value, int):
        raise TypeError(f"{key} must be an int.")
    return value


def _require_str(obj: dict[str, Any], key: str) -> str:
    if key not in obj:
        raise KeyError(f"Missing required field: {key}")
    value = obj[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string.")
    return value


def _parse_epoch_ms(value: int, label: str) -> datetime:
    if not isinstance(value, int):
        raise TypeError(f"{label} must be an int timestamp in milliseconds.")
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _parse_collapse(subitem: dict[str, Any]) -> bool:
    if "collapse" not in subitem:
        return False
    raw = subitem["collapse"]
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        if raw in (0, 1):
            return bool(raw)
    raise TypeError("collapse must be 0/1 or boolean when provided.")


def _has_implies_tag(tags: str) -> bool:
    tokens = tags.split()
    return "@implies" in tokens


def _extract_rule_texts(raw_content: str, *, context: str) -> list[str]:
    text = strip_html(raw_content)
    parts = re.split(r"\s*(=>|=)\s*", text)
    if len(parts) < 3:
        raise ValueError(
            "Rule content must include '=>' or '='. "
            f"context={context} content={text!r}"
        )

    segments = [segment.strip() for segment in parts[0::2]]
    operators = [operator.strip() for operator in parts[1::2]]

    if len(segments) != len(operators) + 1:
        raise ValueError(
            "Rule content must include operators between segments. "
            f"context={context} content={text!r}"
        )

    if any(segment == "" for segment in segments):
        raise ValueError(
            "Rule content must include tokens on both sides. "
            f"context={context} content={text!r}"
        )

    token_groups: list[list[str]] = []
    for segment in segments:
        tokens = [token for token in segment.split() if token]
        if not tokens:
            raise ValueError(
                "Rule content must include tokens on both sides. "
                f"context={context} content={text!r}"
            )
        token_groups.append(tokens)

    rules: set[str] = set()
    current_tokens = token_groups[0]
    for idx, operator in enumerate(operators):
        if operator not in {"=>", "="}:
            raise ValueError(
                "Rule content must use '=>' or '=' operators. "
                f"context={context} content={text!r}"
            )
        next_tokens = token_groups[idx + 1]
        if operator == "=":
            for left in current_tokens:
                for right in next_tokens:
                    if left == right:
                        continue
                    rules.add(f"{left} => {right}")
                    rules.add(f"{right} => {left}")
            merged = list(dict.fromkeys(current_tokens + next_tokens))
            current_tokens = merged
        else:
            for left in current_tokens:
                for right in next_tokens:
                    if left == right:
                        continue
                    rules.add(f"{left} => {right}")
            current_tokens = next_tokens

    return sorted(rules)


def _is_effectively_empty(content: str) -> bool:
    if content.strip() == "":
        return True
    if "<img" in content.lower():
        return False
    return strip_html(content) == ""


def _prepare_database() -> Path:
    db_path = _resolve_sqlite_path(DATABASE_URL)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _delete_existing_db(db_path)
    SafeSession.use_file_db()
    session = SafeSession()
    try:
        insert_default_settings(session.connection())
        session.commit()
    finally:
        session.close()
    return db_path


def _assert_encryption_disabled(payload: dict[str, Any]) -> None:
    encryption = _require_dict(payload, "encryption")
    encrypted = encryption.get("encrypted")
    if encrypted is not False:
        raise ValueError("Legacy export must have encryption.encrypted = false.")


def _import_item(
    db: SafeSession,
    item: dict[str, Any],
    order_map: dict[str | None, list[str]],
    meta: dict[str, NoteMeta],
) -> tuple[int, int]:
    created_ms = _require_int(item, "creation")
    updated_ms = _require_int(item, "last_edit")
    created_at = _parse_epoch_ms(created_ms, "creation")
    updated_at = _parse_epoch_ms(updated_ms, "last_edit")
    if updated_at < created_at:
        raise ValueError("last_edit must be >= creation for each item.")

    subitems = _require_list(item, "subitems")
    if not subitems:
        raise ValueError("Each item must include at least one subitem.")

    indent_stack: list[str] = []
    skipped_indents: list[int] = []
    previous_indent: int | None = None
    root_count = 0

    note_count = 0
    rule_count = 0

    legacy_id = item.get("id", "<unknown>")

    for idx, raw in enumerate(subitems):
        if not isinstance(raw, dict):
            raise TypeError("Each subitem must be an object.")
        indent = _require_int(raw, "indent")
        if indent < 0:
            raise ValueError("indent must be >= 0.")
        if idx == 0 and indent != 0:
            raise ValueError("The first subitem must have indent=0.")
        if indent == 0:
            root_count += 1
            if idx != 0:
                raise ValueError("Only the first subitem may have indent=0.")
        if previous_indent is not None and indent > previous_indent + 1:
            raise ValueError("Indent jumps larger than 1 are not allowed.")

        while skipped_indents and indent <= skipped_indents[-1]:
            skipped_indents.pop()

        effective_indent = indent - len(skipped_indents)
        if effective_indent < 0:
            raise ValueError("Indent underflow after skipping implies notes.")

        while len(indent_stack) > effective_indent:
            indent_stack.pop()
        if len(indent_stack) != effective_indent:
            raise ValueError("Indent stack mismatch; legacy data is malformed.")

        parent_id = indent_stack[-1] if effective_indent > 0 else None
        content = _require_str(raw, "data")
        tags = _require_str(raw, "tags")
        is_collapsed = _parse_collapse(raw)
        context = f"item_id={legacy_id} subitem_index={idx}"

        if _has_implies_tag(tags) and not _is_effectively_empty(content):
            rule_texts = _extract_rule_texts(content, context=context)
            for rule_text in rule_texts:
                insert_rule(
                    db.connection(),
                    rule_text=rule_text,
                    rule_encryption_nonce=None,
                    rule_encryption_tag=None,
                    created_at=created_at,
                    updated_at=updated_at,
                )
                rule_count += 1
            skipped_indents.append(indent)
            previous_indent = indent
            continue

        note_id = str(uuid.uuid4())
        insert_note(
            db.connection(),
            note_id=note_id,
            content=content,
            content_text=strip_html(content),
            encryption_nonce=None,
            encryption_tag=None,
            tags=tags,
            tags_encryption_nonce=None,
            tags_encryption_tag=None,
            parent_id=parent_id,
            prev_id=None,
            next_id=None,
            is_collapsed=is_collapsed,
            created_at=created_at,
            updated_at=updated_at,
        )
        order_map.setdefault(parent_id, []).append(note_id)
        meta[note_id] = NoteMeta(
            parent_id=parent_id,
            is_collapsed=is_collapsed,
            updated_at=updated_at,
        )
        indent_stack.append(note_id)
        previous_indent = indent
        note_count += 1

    if root_count != 1:
        raise ValueError("Each item must contain exactly one indent=0 subitem.")

    return note_count, rule_count


def _apply_order(db: SafeSession, order_map: dict[str | None, list[str]], meta: dict[str, NoteMeta]) -> None:
    for parent_id, ordered_ids in order_map.items():
        if not ordered_ids:
            continue
        for idx, note_id in enumerate(ordered_ids):
            prev_id = ordered_ids[idx - 1] if idx > 0 else None
            next_id = ordered_ids[idx + 1] if idx + 1 < len(ordered_ids) else None
            note_meta = meta[note_id]
            update_links(
                db.connection(),
                note_id,
                updated_at=note_meta.updated_at,
                parent_id=note_meta.parent_id,
                prev_id=prev_id,
                next_id=next_id,
                is_collapsed=note_meta.is_collapsed,
            )


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_path = _resolve_input_path(args.input_path)
    payload = _load_json(input_path)
    _assert_encryption_disabled(payload)
    items = _require_list(payload, "data")

    db_path = _prepare_database()
    print(f"Importing legacy data from {input_path}")
    print(f"Recreated database at {db_path}")

    session = SafeSession()
    note_meta: dict[str, NoteMeta] = {}
    order_map: dict[str | None, list[str]] = {}
    total_notes = 0
    total_rules = 0
    try:
        for raw_item in items:
            if not isinstance(raw_item, dict):
                raise TypeError("Each entry in data must be an object.")
            item_notes, item_rules = _import_item(session, raw_item, order_map, note_meta)
            total_notes += item_notes
            total_rules += item_rules
        _apply_order(session, order_map, note_meta)
        session.commit()
    finally:
        session.close()

    print(f"Imported {len(items)} root items, {total_notes} notes, {total_rules} rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
