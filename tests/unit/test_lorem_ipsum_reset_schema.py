from __future__ import annotations

from datetime import datetime, timezone

from app.db.engine import begin_writer
from app.db.ontology_rules_sql import fetch_all_rules, insert_rule
from app.models.database import SafeSession
from app.security.encryption import set_encryption_required
from lorem_ipsum import reset_schema


def test_reset_schema_drops_ontology_rules_table() -> None:
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
