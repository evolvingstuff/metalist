from __future__ import annotations

from app.db.notes_sql import update_note_fields_preserving_updated_at as db_update_note_fields_preserving_updated_at
from app.db.session import begin_writer
from app.db.settings_sql import fetch_settings
from app.security.encryption import encrypt, is_encryption_available
from app.services.content_cache import cache_note_tags
from app.services.note_store import store as note_store
from app.services.ontology_rules_store import delete_tag_everywhere as delete_tag_from_ontology
from app.services.store import store
from app.services.sync import generate_new_uuid
from app.services.tag_rename import delete_tag_from_tag_bar
from app.services.view_cache import view_cache


def apply_delete_tag_everywhere(*, tag: str, token: str) -> dict:
    if not isinstance(tag, str) or tag.strip() == '':
        raise TypeError('tag must be a non-empty string')
    if not isinstance(token, str):
        raise TypeError('token must be a string')
    if not note_store.loaded:
        raise RuntimeError('NoteStore must be loaded before deleting tags')

    normalized = tag.strip()
    deleted_rule_count = delete_tag_from_ontology(tag=normalized)

    updates: list[tuple[str, str, str]] = []
    for note_id in note_store.list_note_ids():
        record = store.get(note_id)
        updated_tags, changed = delete_tag_from_tag_bar(tags=record.tags, tag=normalized)
        if changed:
            updates.append((note_id, record.content, updated_tags))

    with begin_writer() as connection:
        settings = fetch_settings(connection)
        encryption_enabled = settings is not None and bool(settings["encryption_enabled"])
        if encryption_enabled and not is_encryption_available(token):
            raise RuntimeError('Encryption is enabled but no DEK is available for this token')

        for note_id, _content, tags in updates:
            tags_ciphertext, tags_nonce, tags_tag = encrypt(tags, token)
            if (tags_nonce is None) != (tags_tag is None):
                raise RuntimeError('Encrypted tags must include both nonce and tag')
            db_update_note_fields_preserving_updated_at(
                connection,
                note_id,
                tags=tags_ciphertext,
                tags_encryption_nonce=tags_nonce,
                tags_encryption_tag=tags_tag,
            )

    for note_id, content, tags in updates:
        record = store.get(note_id)
        if record.updated_at is None:
            raise RuntimeError(f"Cannot preserve missing updated_at while deleting tag: {note_id}")
        cache_note_tags(note_id, tags)
        store.update_content_and_tags(note_id, content, tags, updated_at=record.updated_at)

    note_store.rebuild_search_index_tag_terms()
    view_cache.clear()
    return {
        'ok': True,
        'deletedNoteCount': len(updates),
        'deletedRuleCount': deleted_rule_count,
        'updateUUID': generate_new_uuid(),
    }
