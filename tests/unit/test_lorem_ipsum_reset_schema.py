from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess

from app.db.file_session import resolve_file_database_path
from app.db.engine import begin_writer
from app.db.ontology_rules_sql import fetch_all_rules, insert_rule
from app.models.database import SafeSession
from app.security.encryption import set_encryption_required
import pytest
from lorem_ipsum import (
    _SEEDED_IMAGE_MAX_DIMENSION_PX,
    encode_image_as_data_uri,
    reset_schema,
    wipe_database_artifacts,
)


def test_reset_schema_drops_ontology_rules_table(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    set_encryption_required(False)
    SafeSession.use_memory_db()
    try:
        now = datetime.now(timezone.utc)
        with begin_writer() as connection:
            insert_rule(
                connection,
                rule_text="ciphertext",
                rule_encryption_nonce=b"nonce",
                rule_encryption_tag=b"tag",
                created_at=now,
                updated_at=now,
            )

        with begin_writer() as connection:
            rows_before = fetch_all_rules(connection)
        assert rows_before

        reset_schema()

        with begin_writer() as connection:
            rows_after = fetch_all_rules(connection)
        assert rows_after == []
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_wipe_database_artifacts_removes_main_and_file_database_artifacts(tmp_path: Path) -> None:
    database_path = tmp_path / "namespaces" / "default" / "default.metalist.db"
    file_database_path = resolve_file_database_path(database_path)
    artifact_paths = (
        database_path,
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
        file_database_path,
        Path(f"{file_database_path}-wal"),
        Path(f"{file_database_path}-shm"),
    )

    for artifact_path in artifact_paths:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(b"artifact")

    wipe_database_artifacts(database_path)

    assert all(artifact_path.exists() is False for artifact_path in artifact_paths)


@pytest.mark.skipif(shutil.which("sips") is None, reason="requires macOS sips")
def test_encode_image_as_data_uri_resizes_and_reencodes_sample_image(tmp_path: Path) -> None:
    image_path = Path(__file__).resolve().parents[2] / "docs" / "sample_images" / "img1.png"

    data_uri = encode_image_as_data_uri(image_path)

    prefix = '<div><img src="data:image/jpeg;base64,'
    assert data_uri.startswith(prefix)
    assert 'alt="img1"' in data_uri

    encoded_payload = data_uri[len(prefix):].split('" alt="', 1)[0]
    decoded_bytes = base64.b64decode(encoded_payload)
    assert len(decoded_bytes) < image_path.stat().st_size

    resized_path = tmp_path / "resized.jpg"
    resized_path.write_bytes(decoded_bytes)

    metadata_output = subprocess.check_output(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(resized_path)],
        text=True,
    )
    width_match = re.search(r"pixelWidth:\s+(\d+)", metadata_output)
    height_match = re.search(r"pixelHeight:\s+(\d+)", metadata_output)
    assert width_match is not None
    assert height_match is not None
    assert int(width_match.group(1)) <= _SEEDED_IMAGE_MAX_DIMENSION_PX
    assert int(height_match.group(1)) <= _SEEDED_IMAGE_MAX_DIMENSION_PX
