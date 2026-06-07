# Reminder Sounds Plan

## Goal
Add reusable, namespace-local sound assets and let reminders optionally play sounds when they surface and when `Got it` succeeds.

## Decisions To Confirm
- Default caps: 2 MB max upload size and 10 seconds max duration.
- Accepted formats: common browser-playable audio (`audio/mpeg`, `audio/wav`, `audio/ogg`, `audio/webm`, `audio/mp4`, `audio/aac`, `audio/flac`).
- Duration validation: add a small audio metadata dependency (`mutagen`) so the server enforces max duration instead of trusting browser metadata.
- Default sound: provide a built-in, non-deletable `Default chime` option. Uploaded sounds live in the files DB `sounds` table.
- Reminder settings: store popup sound selection/enabled and `Got it` sound selection/enabled on each reminder. New reminder forms start disabled unless the user enables them.
- Deletion behavior: uploaded sounds cannot be deleted while referenced by any reminder's popup or `Got it` sound fields. The user must edit those reminders to another sound, including `Default chime`, before deletion.
- Aggregate cap: 50 MB total uploaded sound library per namespace. Display current usage in the sound manager UI.

## Backend Storage
1. Extend `app/db/file_schema.py` with a separate `sounds` table in the sibling `*.files.db`.
   - Columns: `id`, `title`, `original_filename`, `mime_type`, `size_bytes`, `duration_seconds`, encrypted `metadata_json`, encrypted `blob_data`, encryption nonce/tag fields, `is_builtin`, `created_at`, `updated_at`.
   - Keep the existing `files` table unchanged.
2. Add `app/db/sounds_sql.py` for composable SQLite helpers.
3. Add `app/services/sound_storage.py`.
   - Memory-first `sound_store` loads all sound metadata and blobs at startup for passwordless namespaces and after encrypted hydration for locked namespaces.
   - Playback/list APIs read from memory, not SQLite.
   - Create/list/update-title/delete/download sound assets with write-through persistence.
   - Validate title, MIME type, max byte size, and duration.
   - Enforce the aggregate uploaded-sound byte cap before accepting new sounds.
   - Encrypt/decrypt sound metadata and blobs with the same DEK behavior as `file_storage`.
   - Expose password-transition rewrite helpers so enable/disable password protection rewrites sound rows.
4. Update `app/services/auth_service.py` password transitions to rewrite sounds alongside files.
5. Update backup/restore code if needed so the existing files DB backup naturally includes the new table and restores schema correctly.

## Backend API
1. Add `app/api/routes/sounds.py` under `/api2/sounds`.
   - `GET /api2/sounds` list uploaded sounds plus built-in default.
   - `POST /api2/sounds/upload` upload audio with a required title.
   - `PUT /api2/sounds/{sound_id}` rename uploaded sound.
   - `DELETE /api2/sounds/{sound_id}` delete uploaded sound.
   - `GET /api2/sounds/{sound_id}/play` stream an authenticated sound blob.
2. Reject deletion/rename of built-in sounds loudly.
3. Wire the router in `app/main.py` and add URLs in frontend config/API client.

## Reminder Payload
1. Extend reminder payloads with:
   - `popup_sound_enabled`
   - `popup_sound_id`
   - `ack_sound_enabled`
   - `ack_sound_id`
2. Use a sentinel id such as `builtin.default_chime` for the default sound.
3. Preserve older reminders by normalizing missing sound fields to disabled/default.

## Frontend UI
1. Add a reusable sound manager modal.
   - Upload audio file, title it, list existing sounds, rename/delete uploaded sounds, preview any sound.
   - Show caps in form validation and reject invalid files before upload; server remains authoritative.
2. Add command palette entry: `Manage sounds…`.
3. Extend reminder modal with a compact settings section for:
   - Play sound when reminders pop up.
   - Dropdown selector for the reminder popup sound.
   - Play sound when `Got it` is clicked.
   - Dropdown selector for the `Got it` sound.
4. Keep controls dense and app-native; no instructional landing page.

## Frontend Playback
1. Add `app/static/js/modules/sound-service.js`.
   - Load sound list.
   - Play built-in default chime via Web Audio or stream uploaded sound via authenticated `/api2/sounds/{id}/play`.
   - Use the firing reminder's stored sound fields for one-shot playback on popup render and after successful `Got it`.
2. Handle browser autoplay blocking as an external condition:
   - Do not crash the app on `NotAllowedError`.
   - Record a visible modal-level status only when the user is configuring/previewing sounds.
3. Fail fast for internal bugs: missing sound ids, malformed reminder sound fields, invalid API payloads.

## Tests
1. Python unit tests:
   - Sound upload validation: title, MIME, size, duration.
   - CRUD and authenticated stream path.
   - Encryption/plaintext transitions rewrite sound rows.
   - Reminder payload stores per-reminder sound fields.
   - Built-in sound cannot be renamed/deleted.
2. JS unit tests where existing harness supports it:
   - Per-reminder sound field parsing.
   - Popup render triggers popup sound once per occurrence.
   - `Got it` plays only after successful reminder action.
3. Run targeted tests first, then broader pytest before checkpoint.

## Docs
1. Update `docs/ui/reminders.md` with sound behavior and privacy/autoplay notes.
2. Add or update sound storage docs under `docs/ui/` or `docs/`.
3. Update `docs/AI-SUMMARY.md` after implementation.

## Out Of Scope
- OS/browser push notifications.
- Background playback while the app is closed, hidden, logged out, or locked.
- Audio editing/trimming.
