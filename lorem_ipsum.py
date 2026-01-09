#!/usr/bin/env python3
"""Reinitialize the MetaList database with randomized lorem ipsum content.

This script drops and recreates the local SQLite schema, then seeds a
configurable number of root notes populated with lorem ipsum paragraphs,
embedded sample images, and nested child notes at varying depths.

Usage (default root count = 25):
    python lorem_ipsum.py

Additional options:
    python lorem_ipsum.py --root-count 40 --max-depth 4 --max-children 5
"""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import random
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence
from types import SimpleNamespace

from tqdm import tqdm

from app.config import DATABASE_URL
from app.db.notes_sql import insert_note, update_links
from app.db.schema import APP_SETTINGS_TABLE, NOTES_TABLE, initialize_schema
from app.db.settings_sql import fetch_settings, insert_default_settings
from app.models.database import SafeSession
from app.services.content_cache import cache_note, cache_note_tags, clear_cache
from app.services.note_store import store as note_store
from app.security.encryption import encrypt


default_root_count =  10_000  # 1000
default_child_probability = 0.3
default_image_probability = 0.05

# Static lorem ipsum blocks to keep seeded notes varied
_LOREM_PARAGRAPHS: Sequence[str] = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
    "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
    "Curabitur pretium tincidunt lacus. Nulla gravida orci a odio.",
    "Integer in mauris eu nibh euismod gravida.",
    "Praesent sed nisi eleifend, fermentum orci vel, tempor sapien.",
    "Phasellus gravida semper nisi. Nullam vel sem.",
    "Etiam imperdiet imperdiet orci. Nunc nec neque.",
    "Aenean massa. Cum sociis natoque penatibus et magnis dis parturient montes.",
    "Donec quam felis, ultricies nec, pellentesque eu, pretium quis, sem.",
)


@dataclass
class SeedStats:
    note_count: int = 0
    image_count: int = 0
    deepest_level: int = 0

    def record_note(self, level: int) -> None:
        self.note_count += 1
        if level > self.deepest_level:
            self.deepest_level = level

    def record_images(self, count: int) -> None:
        self.image_count += count


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed MetaList with lorem ipsum content.")
    parser.add_argument(
        "--root-count",
        type=int,
        default=default_root_count,
        help=f"Number of root-level notes to create (default: {default_root_count})",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum depth for nested child notes (default: 3)",
    )
    parser.add_argument(
        "--max-children",
        type=int,
        default=4,
        help="Maximum number of children per note (default: 4)",
    )
    parser.add_argument(
        "--child-probability",
        type=float,
        default=default_child_probability,
        help="fLikelihood (0-1) that a note will spawn children when depth allows (default: {default_child_probability})",
    )
    parser.add_argument(
        "--image-probability",
        type=float,
        default=0.35,
        help="Likelihood (0-1) that a note will include an embedded image (default: 0.35)",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=2,
        help="Maximum number of images per note when selected (default: 2)",
    )
    parser.add_argument(
        "--collapse-probability",
        type=float,
        default=0.2,
        help="Likelihood (0-1) that a note is initially collapsed (default: 0.2)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible content (default: None)",
    )
    return parser.parse_args(argv)


def ensure_sqlite_file() -> Path:
    if not DATABASE_URL.startswith("sqlite///") and not DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError(f"This seeder only supports SQLite, got: {DATABASE_URL}")

    relative = DATABASE_URL.replace("sqlite:///", "", 1)
    db_path = Path(relative)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def reset_schema() -> None:
    session = SafeSession()
    try:
        conn = session.connection()
        conn.execute(f"DROP TABLE IF EXISTS {NOTES_TABLE}")
        conn.execute(f"DROP TABLE IF EXISTS {APP_SETTINGS_TABLE}")
        initialize_schema(conn)
        session.commit()
    finally:
        session.close()


def ensure_default_settings() -> None:
    db = SafeSession()
    try:
        settings = fetch_settings(db.connection())
        if not settings:
            insert_default_settings(db.connection())
            db.commit()
    finally:
        db.close()


def load_sample_images() -> List[Path]:
    project_root = Path(__file__).resolve().parent
    image_dir = project_root / "docs" / "sample_images"
    if not image_dir.exists() or not image_dir.is_dir():
        raise RuntimeError(f"Sample image directory not found: {image_dir}")
    images = sorted(path for path in image_dir.iterdir() if path.is_file())
    if not images:
        raise RuntimeError(f"No image files found in {image_dir}")
    return images


def encode_image_as_data_uri(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(image_path.name)
    if not mime_type:
        raise RuntimeError(f"Unable to determine MIME type for {image_path}")
    data = image_path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    alt_text = html.escape(image_path.stem.replace("_", " "))
    return (
        f'<div><img src="data:{mime_type};base64,{encoded}" '
        f'alt="{alt_text}" /></div>'
    )


def build_note_content(
    rng: random.Random,
    images: Sequence[Path],
    image_probability: float,
    max_images: int,
) -> tuple[str, int]:
    paragraph_count = rng.randint(1, 3)
    paragraphs = rng.sample(_LOREM_PARAGRAPHS, k=paragraph_count)

    parts: List[str] = []
    for paragraph in paragraphs:
        parts.append(f"<div>{html.escape(paragraph)}</div>")
        parts.append("<div><br></div>")

    image_count = 0
    if rng.random() < image_probability:
        image_total = rng.randint(1, max_images)
        chosen = rng.sample(images, k=min(image_total, len(images)))
        for image_path in chosen:
            parts.append(encode_image_as_data_uri(image_path))
            parts.append("<div><br></div>")
        image_count = len(chosen)

    if parts:
        parts.pop()  # Remove trailing spacer for cleaner markup
    content = "".join(parts)
    assert content, "Generated note content should never be empty"
    return content, image_count


ROOT_KEY = "__root__"


def _parent_key(parent_id: str | None) -> str:
    assert parent_id is not None
    return parent_id


def register_note_order(
    order_map: Dict[str, List[str]],
    parent_id: str | None,
    note_id: str,
    rng: random.Random,
) -> None:
    key = _parent_key(parent_id)
    bucket = order_map.setdefault(key, [])
    insert_at = rng.randint(0, len(bucket))
    bucket.insert(insert_at, note_id)


def apply_all_orders(db_session: SafeSession, order_map: Dict[str, List[str]]) -> None:
    for key, ordered_ids in order_map.items():
        if not ordered_ids:
            continue
        assert key != ROOT_KEY
        parent_id = key
        apply_order(db_session, parent_id, ordered_ids)


def apply_order(db_session: SafeSession, parent_id: str | None, ordered_ids: List[str]) -> None:
    for idx, current_id in enumerate(ordered_ids):
        if idx > 0:
            prev_id = ordered_ids[idx - 1]
        else:
            prev_id = None
        if idx < len(ordered_ids) - 1:
            next_id = ordered_ids[idx + 1]
        else:
            next_id = None
        update_links(
            db_session.connection(),
            current_id,
            parent_id=parent_id,
            prev_id=prev_id,
            next_id=next_id,
        )


def create_note(
    db_session,
    rng: random.Random,
    images: Sequence[Path],
    image_probability: float,
    max_images: int,
    collapse_probability: float,
    parent_id: str | None,
    level: int,
    stats: SeedStats,
    child_probability: float,
    max_depth: int,
    max_children: int,
    order_map: Dict[str, List[str]],
) -> None:

    note_id = str(uuid.uuid4())
    content, image_count = build_note_content(rng, images, image_probability, max_images)

    ciphertext, nonce, tag = encrypt(content)
    tags_ciphertext, tags_nonce, tags_tag = encrypt("")
    timestamp = datetime.now(timezone.utc)
    is_collapsed = rng.random() < collapse_probability

    insert_note(
        db_session.connection(),
        note_id=note_id,
        content=ciphertext,
        encryption_nonce=nonce,
        encryption_tag=tag,
        tags=tags_ciphertext,
        tags_encryption_nonce=tags_nonce,
        tags_encryption_tag=tags_tag,
        parent_id=parent_id,
        prev_id=None,
        next_id=None,
        is_collapsed=is_collapsed,
        created_at=timestamp,
        updated_at=timestamp,
    )

    cache_note(note_id, content)
    cache_note_tags(note_id, "")

    if note_store.loaded:
        note_store.add_note_from_db(
            SimpleNamespace(
                id=note_id,
                content=ciphertext,
                encryption_nonce=nonce,
                encryption_tag=tag,
                tags=tags_ciphertext,
                tags_encryption_nonce=tags_nonce,
                tags_encryption_tag=tags_tag,
                parent_id=parent_id,
                prev_id=None,
                next_id=None,
                is_collapsed=is_collapsed,
                created_at=timestamp,
                updated_at=timestamp,
            ),
            content,
            "",
        )

    register_note_order(order_map, parent_id, note_id, rng)

    stats.record_note(level)
    stats.record_images(image_count)

    if level >= max_depth:
        return

    if rng.random() >= child_probability:
        return

    child_total = rng.randint(1, max_children)
    for _ in range(child_total):
        create_note(
            db_session=db_session,
            rng=rng,
            images=images,
            image_probability=image_probability,
            max_images=max_images,
            collapse_probability=collapse_probability,
            parent_id=note_id,
            level=level + 1,
            stats=stats,
            child_probability=child_probability,
            max_depth=max_depth,
            max_children=max_children,
            order_map=order_map,
        )


def seed_notes(args: argparse.Namespace) -> SeedStats:
    rng = random.Random(args.seed)
    images = load_sample_images()
    db = SafeSession()
    stats = SeedStats()
    order_map: Dict[str, List[str]] = {}

    try:
        progress = tqdm(
            range(args.root_count),
            total=args.root_count,
            desc="Seeding root notes",
            unit="root",
        )
        for _ in progress:
            create_note(
                db_session=db,
                rng=rng,
                images=images,
                image_probability=default_image_probability,
                max_images=args.max_images,
                collapse_probability=args.collapse_probability,
                parent_id=None,
                level=0,
                stats=stats,
                child_probability=args.child_probability,
                max_depth=args.max_depth,
                max_children=args.max_children,
                order_map=order_map,
            )
        apply_all_orders(db, order_map)
        db.commit()
    finally:
        db.close()
    return stats


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    db_path = ensure_sqlite_file()
    print(f"Reinitializing database at {db_path}")

    SafeSession.use_file_db()

    clear_cache()
    reset_schema()
    ensure_default_settings()

    stats = seed_notes(args)

    note_store.load_from_db(None)

    print(
        "Seed complete:\n"
        f"  Root notes: {args.root_count}\n"
        f"  Total notes: {stats.note_count}\n"
        f"  Embedded images: {stats.image_count}\n"
        f"  Deepest level: {stats.deepest_level}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
