from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from app.db.engine import GuardedConnection, begin_writer
from app.db.ontology_rules_sql import fetch_all_rules, insert_rule
from app.models.database import SafeSession
from app.security.encryption import clear_encryption_key, encrypt, set_encryption_required
from app.services.ontology_rules_store import (
    bootstrap_ontology_rules_store,
    create_rule_line,
    delete_rule_line,
    ensure_rules_decrypted_and_compiled,
    get_ontology,
    list_rule_lines,
    update_rule_line,
)
from app.services.tokens import token_service


def test_ontology_rules_store_bootstrap_and_crud() -> None:
    set_encryption_required(False)
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
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_ontology_rules_store_respects_read_guard() -> None:
    set_encryption_required(False)
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
            bootstrap_ontology_rules_store(connection=connection)

        SafeSession.enable_read_guard()
        try:
            session = SafeSession()
            try:
                guarded = GuardedConnection(session.connection())
                with pytest.raises(RuntimeError, match="Post-startup DB read forbidden"):
                    fetch_all_rules(guarded)
            finally:
                session.close()

            rules_by_id = dict(list_rule_lines())
            assert rules_by_id

            ontology = get_ontology()
            inferred = ontology.infer_effective_tags(base_tags=frozenset({"alpha"}), plaintext="")
            assert "beta" in inferred

            created_id, _ = create_rule_line(text="beta => gamma", token="")
            update_rule_line(rule_id=created_id, text="beta => delta", token="")
            delete_rule_line(rule_id=created_id)
        finally:
            SafeSession.disable_read_guard()
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_ontology_rules_store_encrypted_bootstrap_and_decrypt() -> None:
    set_encryption_required(True)
    SafeSession.use_memory_db()
    token_service.reset()
    clear_encryption_key()
    try:
        dek = os.urandom(32)
        token = token_service.create_token(client_info="test", owner_tab_id="tab", dek=dek)
        ciphertext, nonce, tag = encrypt("alpha => beta", token)
        assert nonce is not None
        assert tag is not None
        assert ciphertext != "alpha => beta"

        now = datetime.now(timezone.utc)
        with begin_writer() as connection:
            insert_rule(
                connection,
                rule_text=ciphertext,
                rule_encryption_nonce=nonce,
                rule_encryption_tag=tag,
                created_at=now,
                updated_at=now,
            )
            bootstrap_ontology_rules_store(connection=connection)

        with pytest.raises(RuntimeError, match="not decrypted"):
            get_ontology()

        ensure_rules_decrypted_and_compiled(token=token)
        ontology = get_ontology()
        inferred = ontology.infer_effective_tags(base_tags=frozenset({"alpha"}), plaintext="")
        assert "beta" in inferred
        rules_by_id = dict(list_rule_lines())
        assert "alpha => beta" in rules_by_id.values()

        created_id, _ = create_rule_line(text="beta => gamma", token=token)
        with begin_writer() as connection:
            stored = [row for row in fetch_all_rules(connection) if row["id"] == created_id]
        assert len(stored) == 1
        stored_row = stored[0]
        assert stored_row["rule_encryption_nonce"] is not None
        assert stored_row["rule_encryption_tag"] is not None
        assert stored_row["rule_text"] != "beta => gamma"
    finally:
        set_encryption_required(False)
        token_service.reset()
        clear_encryption_key()
        SafeSession.use_file_db()
