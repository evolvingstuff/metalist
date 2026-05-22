from __future__ import annotations

from dataclasses import dataclass

from app.db.session import begin_writer
from app.db.notes_sql import update_note_fields_preserving_updated_at as db_update_note_fields_preserving_updated_at
from app.db.settings_sql import fetch_settings
from app.security.encryption import is_encryption_available, encrypt
from app.services.content_cache import cache_note_tags
from app.services.note_store import store as note_store
from app.services.ontology_rules_store import rename_tag_everywhere
from app.services.store import store
from app.services.sync import generate_new_uuid
from app.services.tag_rename import rename_tag_in_tag_bar
from app.services.view_cache import view_cache


def apply_rename_tag_everywhere(*, old: str, new: str, token: str) -> dict:
    if not isinstance(old, str) or old.strip() == "":
        raise TypeError('old must be a non-empty string')
    if not isinstance(new, str) or new.strip() == "":
        raise TypeError('new must be a non-empty string')
    if not isinstance(token, str):
        raise TypeError('token must be a string')

    old_tag = old.strip()
    new_tag = new.strip()
    if old_tag == new_tag:
        raise ValueError('old and new must differ')

    if not note_store.loaded:
        raise RuntimeError('NoteStore must be loaded before renaming tags')

    rename_tag_everywhere(old=old_tag, new=new_tag, token=token)

    updates: list[tuple[str, str, str]] = []
    for note_id in note_store.list_note_ids():
        record = store.get(note_id)
        updated, changed = rename_tag_in_tag_bar(tags=record.tags, old=old_tag, new=new_tag)
        if not changed:
            continue
        updates.append((note_id, record.content, updated))

    with begin_writer() as connection:
        settings = fetch_settings(connection)
        encryption_enabled = False
        if settings is not None:
            encryption_enabled = bool(settings["encryption_enabled"])

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
            raise RuntimeError(f"Cannot preserve missing updated_at while renaming tag: {note_id}")
        cache_note_tags(note_id, tags)
        store.update_content_and_tags(note_id, content, tags, updated_at=record.updated_at)

    view_cache.clear()
    update_uuid = generate_new_uuid()
    return {
        'ok': True,
        'renamedNoteCount': len(updates),
        'updateUUID': update_uuid,
    }
