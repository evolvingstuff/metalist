#!/usr/bin/env python3
"""Inspect MetaList SQLite database for linked-list and hierarchy anomalies."""

import argparse
import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze MetaList note database")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument("--note-id", help="Specific note UUID to inspect deeply")
    return parser.parse_args()


def connect(db_path: str) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_notes(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    query = (
        "SELECT id, parent_id, prev_id, next_id, is_collapsed, "
        "length(content) AS ciphertext_len, "
        "encryption_nonce IS NOT NULL AS has_nonce, "
        "encryption_tag IS NOT NULL AS has_tag, "
        "created_at, updated_at "
        "FROM notes"
    )
    return list(conn.execute(query))


def summarize(notes: List[sqlite3.Row]) -> None:
    total = len(notes)
    root = sum(1 for row in notes if row["parent_id"] is None)
    print("=== Database Summary ===")
    print(f"Total notes        : {total}")
    print(f"Root notes         : {root}")
    print(f"Encrypted notes    : {sum(1 for row in notes if row['has_nonce'])}")
    empty_cipher = [row for row in notes if row["ciphertext_len"] in (None, 0)]
    if empty_cipher:
        print(f"WARNING: {len(empty_cipher)} notes have empty ciphertext")
    dangling = sorted({row["parent_id"] for row in notes if row["parent_id"] and not any(n["id"] == row["parent_id"] for n in notes)})
    if dangling:
        print("CRITICAL: Dangling parent references detected ->", ", ".join(dangling))
    print()


def validate_parent_group(parent_id: str, children: List[sqlite3.Row], index: Dict[str, sqlite3.Row]) -> List[str]:
    issues: List[str] = []
    if not children:
        return issues
    id_map = {row["id"]: row for row in children}
    heads = [row for row in children if row["prev_id"] is None]
    tails = [row for row in children if row["next_id"] is None]
    if len(heads) != 1:
        issues.append(f"parent {parent_id or 'ROOT'}: expected 1 head, found {len(heads)}")
    if len(tails) != 1:
        issues.append(f"parent {parent_id or 'ROOT'}: expected 1 tail, found {len(tails)}")
    for row in children:
        prev_id = row["prev_id"]
        next_id = row["next_id"]
        if prev_id and prev_id not in id_map:
            issues.append(f"parent {parent_id or 'ROOT'}: note {row['id']} prev_id {prev_id} missing")
        if next_id and next_id not in id_map:
            issues.append(f"parent {parent_id or 'ROOT'}: note {row['id']} next_id {next_id} missing")
    if heads:
        current = heads[0]
        visited: List[str] = []
        seen = set()
        while current:
            node_id = current["id"]
            if node_id in seen:
                issues.append(f"parent {parent_id or 'ROOT'}: cycle detected at {node_id}")
                break
            seen.add(node_id)
            visited.append(node_id)
            next_id = current["next_id"]
            if next_id is None:
                break
            if next_id not in id_map:
                issues.append(f"parent {parent_id or 'ROOT'}: chain jumps to missing {next_id}")
                break
            current = id_map[next_id]
        if len(seen) != len(children):
            missing = sorted({row["id"] for row in children} - seen)
            issues.append(f"parent {parent_id or 'ROOT'}: disconnected nodes {missing}")
    return issues


def collect_children(notes: List[sqlite3.Row]) -> Dict[str, List[sqlite3.Row]]:
    grouped: Dict[str, List[sqlite3.Row]] = defaultdict(list)
    for row in notes:
        grouped[row["parent_id"]].append(row)
    return grouped


def print_tree(parent_id: str, grouped: Dict[str, List[sqlite3.Row]], depth: int = 0) -> None:
    children = grouped[parent_id]
    if not children:
        return
    heads = [row for row in children if row["prev_id"] is None]
    head = None
    if heads:
        head = heads[0]
    if head is None:
        for row in children:
            prefix = "  " * depth
            print(f"{prefix}- {row['id']} [unordered] children={len(grouped[row['id']])}")
            print_tree(row["id"], grouped, depth + 1)
        return
    current = head
    visited = set()
    while current:
        node_id = current["id"]
        prefix = "  " * depth
        print(
            f"{prefix}- {node_id} prev={current['prev_id'] or 'None'} next={current['next_id'] or 'None'} "
            f"children={len(grouped[node_id])} ciphertext_len={current['ciphertext_len']}"
        )
        print_tree(node_id, grouped, depth + 1)
        visited.add(node_id)
        next_id = current["next_id"]
        if next_id is None:
            break
        if next_id in visited:
            print(f"{prefix}  !! cycle back to {next_id}")
            break
        peers = grouped[parent_id]
        next_row = next((row for row in peers if row["id"] == next_id))
        if next_row is None:
            print(f"{prefix}  !! missing next node {next_id}")
            break
        current = next_row


def inspect_note(note_id: str, index: Dict[str, sqlite3.Row], grouped: Dict[str, List[sqlite3.Row]]) -> None:
    note = index.get(note_id)
    if note is None:
        print(f"Note {note_id} not found")
        return
    print("=== Target Note ===")
    print(f"id           : {note['id']}")
    print(f"parent_id    : {note['parent_id']}")
    print(f"prev_id      : {note['prev_id']}")
    print(f"next_id      : {note['next_id']}")
    print(f"ciphertextlen: {note['ciphertext_len']}")
    print(f"has_nonce    : {bool(note['has_nonce'])}")
    print(f"has_tag      : {bool(note['has_tag'])}")
    print(f"created_at   : {note['created_at']}")
    print(f"updated_at   : {note['updated_at']}")
    siblings = grouped[note["parent_id"]]
    if siblings:
        ordered = []
        head = next((row for row in siblings if row["prev_id"] is None))
        current = head
        seen = set()
        while current:
            ordered.append(current["id"])
            seen.add(current["id"])
            nxt = current["next_id"]
            if nxt is None:
                break
            current = next((row for row in siblings if row["id"] == nxt))
            if current is None or current["id"] in seen:
                break
        print(f"siblings order: {ordered}")
    child_ids = [row["id"] for row in grouped[note_id]]
    print(f"child ids     : {child_ids}")
    print()


def main() -> None:
    args = parse_args()
    conn = connect(args.db)
    notes = fetch_notes(conn)
    if not notes:
        raise SystemExit("No notes found in database")
    summarize(notes)
    grouped = collect_children(notes)
    index: Dict[str, sqlite3.Row] = {row["id"]: row for row in notes}
    issues: List[str] = []
    for parent_id, children in grouped.items():
        issues.extend(validate_parent_group(parent_id, children, index))
    if issues:
        print("=== Linked List Issues ===")
        for item in issues:
            print(f"- {item}")
        print()
    else:
        print("Linked list structure appears consistent.\n")
    print("=== Tree Snapshot ===")
    print_tree(None, grouped)
    print()
    if args.note_id:
        inspect_note(args.note_id, index, grouped)


if __name__ == "__main__":
    main()
