# Encrypted File Attachments Plan

## Goal
- Add first-class file attachments referenced by UUID from notes.
- Store files in a separate SQLite database layer, with plaintext UUID indexing but encrypted-at-rest payload + metadata.
- Do not preload file rows/blob data into server memory on startup.
- Decrypt file rows only when a request needs to send metadata/content to the browser.
- Keep unreferenced files until an explicit trim action removes them.

## Working Assumptions
- File references will reuse UUID-based reference resolution rather than introducing a second visible token grammar.
- `files.id` stays plaintext/indexed so startup can build the valid-file UUID set without decrypting every row.
- File title, filename, MIME type, metadata JSON, and blob bytes are encrypted at rest.
- “File-type thumbnails” means deterministic type badges/icons (PDF/image/text/other), not binary preview generation in v1.
- The current live note DB path is derived from `DATABASE_URL` and today resolves to `~/MetaList/metalist2.db`; backups live under `~/MetaList/backups/`.
- There is also an older `~/MetaList/metalist.db` on disk, so the new file-store path must be tied to the active note DB path, not inferred by scanning the directory.
- Existing in-flight changes on this branch are unrelated and should be left intact.

## Architecture Changes

### 1. Separate file DB + shard-ready routing
- Derive the file-store root from the active note DB path (`SafeSession._db_path`) instead of adding another unrelated hardcoded home-directory path.
- Proposed layout:
  - live notes DB: `<db_parent>/<db_stem>.db` (currently `~/MetaList/metalist2.db`)
  - file shard directory: `<db_parent>/<db_stem>.files/`
  - first file shard: `<db_parent>/<db_stem>.files/shard-000.db`
  - backups remain under `<db_parent>/backups/`
- In test mode, this should mirror the active test DB path, e.g. `./test.db` -> `./test.files/shard-000.db`.
- Introduce a file-db access layer isolated from `SafeSession` note traffic:
  - `app/db/file_schema.py`
  - `app/db/file_session.py`
  - `app/db/files_sql.py`
  - `app/services/file_shards.py` or equivalent router abstraction
- Start with one shard/database but keep the router interface keyed by file UUID so additional shards can be added later without rewriting callers.

### 2. File schema
- Create a `files` table with:
  - `id TEXT PRIMARY KEY`
  - encrypted `title`
  - encrypted original filename
  - encrypted MIME type
  - encrypted metadata JSON
  - encrypted blob bytes
  - blob encryption nonce/tag columns
  - metadata encryption nonce/tag columns
  - `size_bytes`
  - `created_at`
  - `updated_at`
- Add indexes needed for UUID existence checks and trim scans.
- Keep the row even when there are zero note references.

### 3. Startup/runtime indexing
- Add an in-memory `FileRegistry` service that stores only known file UUIDs, shard mapping, and cheap non-secret facts if needed.
- On startup:
  - initialize file DB schema
  - scan only file UUIDs from all file shards
  - populate `FileRegistry`
- Do not decrypt file metadata/blob data during startup or login hydration.
- On backup restore or auth reset, rebuild the file UUID registry the same way note runtime state is rebuilt.

### 4. Encryption/decryption flow
- Reuse the existing DEK/session encryption model for files.
- Encrypt file metadata and bytes on insert/update.
- Decrypt on demand for:
  - file card/reference rendering when metadata is needed
  - file download/stream responses
- Fail hard if encrypted file rows are encountered without an active DEK.

### 5. Reference parsing/rendering
- Extend reference resolution so a UUID can resolve to either:
  - a note in `NoteStore`
  - a file in `FileRegistry`
- Add file reference rendering behavior for view mode:
  - title
  - file-type badge/icon
  - metadata summary (type/size, possibly filename)
  - click/download affordance
- Keep edit mode literal, same as note references today.
- Missing file UUIDs should render a missing-reference marker analogous to missing notes.

### 6. API surface
- Add dedicated file routes, likely under `/api2/files`:
  - upload/create file
  - fetch file metadata card data
  - download/stream decrypted file bytes
  - trim unused files
- Keep route models strict: required fields only unless you explicitly approve an optional field later.
- Ensure note snapshot/view payloads can include file reference payloads without forcing full blob transfer.

### 7. Frontend
- Add upload UX for inserting file references into note content.
- Add file reference rendering in the note view layer.
- Add MIME/type icon mapping on the client.
- Add a command-palette utility action under `Cmd/Ctrl + /`:
  - `Trim unused files`
  - confirm destructive behavior
  - refresh view after completion
- Update API client and palette endpoint registry/controller wiring.

### 8. Trim semantics
- Implement a trim service that:
  - scans decrypted note content/reference tokens
  - computes the set of referenced file UUIDs
  - deletes file rows absent from that set
  - refreshes `FileRegistry`
- Trimming is the only automatic deletion path for orphaned files.
- Removing all references from notes must not delete the file.
- Undo/redo of note edits remains safe because orphaned files persist until trim is explicitly run.

### 9. Backup/restore
- Extend backup/restore so file DB state is included with note DB state.
- Backup discovery should start from the active note DB path and include the sibling `<db_stem>.files/` shard directory.
- Treat a backup as incomplete if it omits file shards once this feature exists.
- Restore should rebuild both note runtime state and file UUID registry.

## Implementation Order
1. Add config + shard-ready file DB/session/schema helpers.
2. Add `FileRegistry` + startup bootstrap path.
3. Add encrypted file persistence service + tests.
4. Add file API routes for upload/metadata/download.
5. Extend reference parsing/rendering and note snapshot payloads for files.
6. Add frontend upload/render/download UI.
7. Add trim-unused-files backend service + command-palette action.
8. Extend backup/restore for multi-DB snapshots.
9. Update docs and summary files.

## Tests
- Python unit tests:
  - file schema bootstrap
  - encrypt/decrypt file rows
  - startup UUID-only registry scan
  - file metadata fetch without global preload
  - download path decrypts on demand
  - trim deletes only unreferenced files
  - restore/backup coverage for second DB
- Existing reference-render tests should gain file cases.
- JS/unit tests:
  - command palette registry includes trim action
  - file reference rendering/type badge behavior
- Sanity:
  - run targeted pytest/tests first
  - run `./sanitycheck/run` if present before feature completion

## Docs To Update
- `docs/ui/references.md`
- `docs/ui/command-palette.md`
- `docs/AI-SUMMARY.md`
- backup docs if the restore/backup behavior changes visibly

## Risks / Watch Items
- Backup/restore is easy to miss and would silently lose file data if not updated.
- The repository already has both `metalist.db` and `metalist2.db` in `~/MetaList`; path derivation must anchor to the configured live DB and never “pick one” by directory scan.
- UUID-only file resolution means note/file identity lookup must stay deterministic and collision-safe.
- Large file downloads must avoid accidentally stuffing decrypted blobs into long-lived caches.
- Startup/read-guard behavior for the second DB needs the same fail-fast discipline as the primary DB.
