#!/usr/bin/env python3
"""Import legacy MetaList JSON exports into the current SQLite schema.

This script deletes the existing SQLite database referenced by
`app.config.DATABASE_URL`, recreates the schema, and imports notes from the
legacy JSON format. Use with care: this is destructive.
"""

from __future__ import annotations

import argparse
import getpass
import html
import importlib.util
import json
import sys
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

tk = None  # type: ignore[assignment]
filedialog = None  # type: ignore[assignment]
_TK_IMPORT_ERROR = None

if importlib.util.find_spec("tkinter") is not None:
    import tkinter as tk
    from tkinter import filedialog
else:
    _TK_IMPORT_ERROR = RuntimeError("tkinter is not available")

from app.config import DATABASE_URL
from app.db.notes_sql import insert_note, update_links
from app.db.ontology_rules_sql import insert_rule
from app.db.settings_sql import insert_default_settings
from app.models.database import SafeSession
from app.services.auth_service import AuthService
from app.utils.text_utils import strip_html


_OPEN_TO_CLOSE = {
    "[": "]",
    "{": "}",
    "(": ")",
}
_MAX_DELIMITER_DEPTH = 3
_INLINE_MATH_LATEX_SIGNAL_RE = re.compile(r"[\\\\{}_^]")
_INLINE_MATH_OPERATOR_RE = re.compile(r"[=+\-*/<>]")
_INLINE_MATH_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_INLINE_MATH_TOKEN_RE = re.compile(r"^[A-Za-z0-9(){}_^,./+=<>*\[\]\-]+$")


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
    root = tk.Tk()
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


def _prompt_for_password() -> str | None:
    response = input("Enable password protection? [y/N]: ").strip().lower()
    if response not in {"y", "yes"}:
        return None

    while True:
        password = getpass.getpass("Enter new password: ")
        if password == "":
            print("Password cannot be empty.")
            continue
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("Passwords do not match. Please try again.")
            continue
        return password


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


def _tokenize_tag_bar(tags: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(tags):
        while index < len(tags) and tags[index].isspace():
            index += 1
        if index >= len(tags):
            break

        if tags.startswith("/*", index):
            end = tags.find("*/", index + 2)
            if end == -1:
                break
            index = end + 2
            continue

        start = index
        opener = tags[index]
        if opener in _OPEN_TO_CLOSE:
            opener_run = 1
            while index + opener_run < len(tags) and tags[index + opener_run] == opener:
                opener_run += 1
            if opener_run <= _MAX_DELIMITER_DEPTH:
                closer = _OPEN_TO_CLOSE[opener]
                needle = closer * opener_run
                close_at = tags.find(needle, index + opener_run)
                if close_at != -1:
                    index = close_at + opener_run
                    token = tags[start:index]
                    if token:
                        tokens.append(token)
                    continue

        while index < len(tags) and not tags[index].isspace():
            index += 1
        token = tags[start:index]
        if token:
            tokens.append(token)
    return tokens


def _unwrap_tag_token(token: str) -> tuple[str, tuple[str, int] | None]:
    if not token:
        return token, None

    opener = token[0]
    if opener not in _OPEN_TO_CLOSE:
        return token, None

    opener_run = 1
    while opener_run < len(token) and token[opener_run] == opener:
        opener_run += 1
    if opener_run > _MAX_DELIMITER_DEPTH:
        return token, None
    depth = opener_run

    closer = _OPEN_TO_CLOSE[opener]
    if len(token) < depth * 2:
        return token, None

    if token[-1] != closer:
        return token, None

    closer_run = 1
    while closer_run < len(token) and token[-(closer_run + 1)] == closer:
        closer_run += 1
    if closer_run != depth:
        return token, None

    if token[-depth:] != closer * depth:
        return token, None

    inner = token[depth:-depth]
    if not inner:
        return token, None

    return inner, (opener, depth)


def _has_implies_tag(tags: str) -> bool:
    tokens = tags.split()
    return "@implies" in tokens


def _split_rule_lines(raw_content: str) -> list[str]:
    text = raw_content
    if "<" in text and ">" in text:
        text = re.sub(r"(?i)<\s*br\s*/?>", "\n", text)
        text = re.sub(
            r"(?i)<\s*/?\s*(div|p|li|h[1-6])\b[^>]*>",
            "\n",
            text,
        )
        text = re.sub(r"(?is)<[^>]+>", "", text)
    text = html.unescape(text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract_rule_texts_from_line(line: str, *, context: str) -> list[str]:
    parts = re.split(r"\s*(=>|=)\s*", line)
    if len(parts) < 3:
        return []

    segments = [segment.strip() for segment in parts[0::2]]
    operators = [operator.strip() for operator in parts[1::2]]

    if len(segments) != len(operators) + 1:
        return []

    token_groups: list[list[str]] = []
    for segment in segments:
        tokens = [token for token in segment.split() if token]
        if not tokens:
            return []
        token_groups.append(tokens)

    rules: set[str] = set()
    current_tokens = token_groups[0]
    for idx, operator in enumerate(operators):
        next_tokens = token_groups[idx + 1]
        if operator == "=":
            for left in current_tokens:
                for right in next_tokens:
                    if left == right:
                        continue
                    rules.add(f"{left} => {right}")
                    rules.add(f"{right} => {left}")
            current_tokens = [next_tokens[-1]]
            continue
        if operator == "=>":
            for left in current_tokens:
                for right in next_tokens:
                    if left == right:
                        continue
                    rules.add(f"{left} => {right}")
            current_tokens = next_tokens
            continue
        raise ValueError(
            "Rule content must use '=>' or '=' operators. "
            f"context={context} content={line!r}"
        )

    return sorted(rules)


def _extract_rule_texts(raw_content: str, *, context: str) -> list[str]:
    lines = _split_rule_lines(raw_content)
    rules: set[str] = set()
    for idx, line in enumerate(lines, start=1):
        rules.update(_extract_rule_texts_from_line(line, context=f"{context} line={idx}"))
    return sorted(rules)




def _is_effectively_empty(content: str) -> bool:
    if content.strip() == "":
        return True
    if "<img" in content.lower():
        return False
    return strip_html(content) == ""


def _is_escaped(text: str, index: int) -> bool:
    count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        count += 1
        cursor -= 1
    return count % 2 == 1


def _find_closing_delimiter(text: str, start_index: int, delimiter: str) -> int:
    cursor = start_index
    while cursor < len(text):
        if text.startswith(delimiter, cursor) and not _is_escaped(text, cursor):
            return cursor
        cursor += 1
    return -1


def _find_inline_closing(text: str, start_index: int, max_newlines: int) -> int:
    cursor = start_index
    newline_count = 0
    while cursor < len(text):
        if text[cursor] == "\n":
            newline_count += 1
            if newline_count > max_newlines:
                return -1
        if text[cursor] == "$" and not _is_escaped(text, cursor) and text[cursor + 1 : cursor + 2] != "$":
            if cursor + 1 < len(text) and text[cursor + 1].isdigit():
                cursor += 1
                continue
            return cursor
        cursor += 1
    return -1


def _inline_math_looks_valid(content: str) -> bool:
    stripped = content.strip()
    if stripped == "":
        return False
    if _INLINE_MATH_LATEX_SIGNAL_RE.search(stripped) is not None:
        return True
    has_space = any(ch.isspace() for ch in stripped)
    if not has_space:
        if re.fullmatch(r"[A-Za-z]{1,4}", stripped):
            return True
        if _INLINE_MATH_TOKEN_RE.fullmatch(stripped):
            if _INLINE_MATH_OPERATOR_RE.search(stripped) is not None:
                return True
            if any(ch in "[](){}_^" for ch in stripped):
                return True
            if any(ch.isdigit() for ch in stripped):
                return True
        return False
    if _INLINE_MATH_WORD_RE.search(stripped) is not None:
        return False
    if _INLINE_MATH_OPERATOR_RE.search(stripped) is not None:
        return True
    if any(ch in "[](){}_^" for ch in stripped):
        return True
    return False


def _wrap_latex_segments(text: str) -> tuple[str, bool]:
    output: list[str] = []
    cursor = 0
    found = False
    while cursor < len(text):
        if text.startswith("$$", cursor) and not _is_escaped(text, cursor):
            close_index = _find_closing_delimiter(text, cursor + 2, "$$")
            if close_index != -1:
                segment = text[cursor : close_index + 2]
                output.append(f"[[{segment}]]")
                found = True
                cursor = close_index + 2
                continue
        if text[cursor] == "$" and not _is_escaped(text, cursor) and text[cursor + 1 : cursor + 2] != "$":
            close_index = _find_inline_closing(text, cursor + 1, max_newlines=3)
            if close_index != -1:
                inner = text[cursor + 1 : close_index]
                if _inline_math_looks_valid(inner):
                    segment = text[cursor : close_index + 1]
                    output.append(f"[[{segment}]]")
                    found = True
                    cursor = close_index + 1
                    continue
            output.append(text[cursor])
            cursor += 1
            continue
        output.append(text[cursor])
        cursor += 1
    return "".join(output), found


def _has_global_tag(tags: str, tag_name: str) -> bool:
    token_name = tag_name.casefold()
    for token in _tokenize_tag_bar(tags):
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is not None:
            continue
        if not base.startswith("@"):
            continue
        if base[1:].casefold() == token_name:
            return True
    return False


def _has_tag_anywhere(tags: str, tag_name: str) -> bool:
    token_name = tag_name.casefold()
    for token in _tokenize_tag_bar(tags):
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is None:
            if base.startswith("@") and base[1:].casefold() == token_name:
                return True
            continue
        inner_tokens = [inner for inner in base.split() if inner]
        for inner in inner_tokens:
            if not inner.startswith("@"):
                continue
            if inner[1:].casefold() == token_name:
                return True
    return False


def _has_scoped_renderer(tags: str, tag_name: str, opener: str, depth: int) -> bool:
    token_name = tag_name.casefold()
    for token in _tokenize_tag_bar(tags):
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is None:
            continue
        opener_char, wrapper_depth = wrapper
        if opener_char != opener or wrapper_depth != depth:
            continue
        inner_tokens = [inner for inner in base.split() if inner]
        for inner in inner_tokens:
            if not inner.startswith("@"):
                continue
            if inner[1:].casefold() == token_name:
                return True
    return False


def _append_tag_token(tags: str, token: str) -> str:
    stripped = tags.strip()
    if stripped == "":
        return token
    return f"{stripped} {token}"


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
    if "encrypted" not in encryption:
        raise KeyError("Missing required field: encryption.encrypted")
    if encryption["encrypted"] is not False:
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

    legacy_id = _require_int(item, "id")

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

        if effective_indent > 0:
            parent_id = indent_stack[-1]
        else:
            parent_id = None
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

        content, has_latex = _wrap_latex_segments(content)
        if has_latex:
            if not _has_global_tag(tags, "markdown"):
                tags = _append_tag_token(tags, "@markdown")
            if not _has_scoped_renderer(tags, "latex", "[", 2):
                tags = _append_tag_token(tags, "[[@LaTeX]]")
        if _has_tag_anywhere(tags, "monospace"):
            if not _has_global_tag(tags, "copyable"):
                tags = _append_tag_token(tags, "@copyable")

        note_id = str(uuid.uuid4())
        insert_note(
            db.connection(),
            note_id=note_id,
            content=content,
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
            if idx > 0:
                prev_id = ordered_ids[idx - 1]
            else:
                prev_id = None
            if idx + 1 < len(ordered_ids):
                next_id = ordered_ids[idx + 1]
            else:
                next_id = None
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


def _enable_password(password: str) -> None:
    session = SafeSession()
    try:
        auth = AuthService(session)
        success, message = auth.set_password(password)
        if not success:
            raise RuntimeError(message)
        session.commit()
        print(message)
    finally:
        session.close()


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_path = _resolve_input_path(args.input_path)
    payload = _load_json(input_path)
    password = _prompt_for_password()
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

    if password is not None:
        _enable_password(password)

    print(f"Imported {len(items)} root items, {total_notes} notes, {total_rules} rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
