from __future__ import annotations

from datetime import datetime, timezone

from app.db.engine import begin_writer
from app.db.ontology_rules_sql import insert_rule
from app.models.database import SafeSession
from app.services.ontology_rules_store import (
    bootstrap_ontology_rules_store,
    create_rule_line,
    delete_rule_line,
    get_ontology,
    list_rule_lines,
    update_rule_line,
)


def test_ontology_rules_store_bootstrap_and_crud() -> None:
    SafeSession.use_memory_db()
    try:
        now = datetime.now(timezone.utc)
        with begin_writer() as connection:
            insert_rule(
                connection,
                rule_text="alpha => beta",
                rule_encryption_nonce=None,
                rule_encryption_tag=None,
                created_at=now,
                updated_at=now,
            )

        with begin_writer() as connection:
            bootstrap_ontology_rules_store(connection=connection)

        ontology = get_ontology()
        inferred = ontology.infer_effective_tags(base_tags=frozenset({"alpha"}), plaintext="")
        assert "beta" in inferred

        created_id, _ = create_rule_line(text="beta => gamma", token="")
        rules_by_id = dict(list_rule_lines())
        assert rules_by_id[created_id] == "beta => gamma"

        update_rule_line(rule_id=created_id, text="beta => delta", token="")
        updated_rules = dict(list_rule_lines())
        assert updated_rules[created_id] == "beta => delta"

        delete_rule_line(rule_id=created_id)
        final_rules = dict(list_rule_lines())
        assert created_id not in final_rules
    finally:
        SafeSession.use_file_db()

