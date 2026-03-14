# AI-SUMMARY

## Project: MetaList
- Single-user FastAPI app for hierarchical notes with SSR + a diff-based `POST /api2/notes/view`.

## Architecture
- Entry: `main.py` - runs Uvicorn (`app.main:app`) with access-log noise filtering.
- Startup bootstrap: `main.py` now resolves `--namespace`, `--port`, `--https-port`, and `--mcp-port` before importing `app.main`, so import-time config sees the right DB path and listener ports.
- `app/main.py`: FastAPI wiring, middleware, startup bootstrapping, SSR templates.
- `app/api/routes`: JSON routers mounted under `API_PREFIX` (default `/api2`).
  - `app/api/routes/notes.py`
  - `app/api/routes/auth.py`
  - `app/api/routes/memory.py`
  - `app/api/routes/files.py`
- `app/api/middleware/auth.py`: Auth middleware gating routes when a password exists.
- `app/usecases`: Cmd* application commands (transport-agnostic orchestration).
- `app/services`: Auth, tokens, cache, sync, undo, integrity, note store, file storage, snapshots, tab state cache.
- `app/services/note_store.py`: Canonical in-memory store for decrypted notes + parent/prev/next links.
- `app/services/file_storage.py`: Stores file attachments in a sibling `*.files.db` SQLite database; uses plaintext rows when the app has no password and encrypted metadata/blob rows when the app is in encrypted mode.
- `app/services/file_registry.py`: In-memory registry of valid file UUIDs only; startup bootstraps this without hydrating file rows/blobs.
- Notes schema: `notes.content` + `notes.tags` are persisted; tags are a space-separated string.
- `app/services/snapshot.py`: Builds the view snapshot used by `/api2/notes/view`.
- `app/services/content_formatting.py`: Applies view-only meta-tag formatting (`@monospace`, `@red`) with optional wrapper scoping.
- `app/services/embedded_references.py`: Resolves note/file UUID references in view mode (embedded notes, note previews, file cards, missing/cycle markers).
- `app/services/tab_state.py`: Tracks `(client, tab)` search + scroll metadata used by the UI between reloads.
- `app/services/login_rate_limit.py`: In-memory login attempt throttling for `/api2/auth/login`.
- `app/services/runtime_hardening.py`: Startup hardening (disable core dumps; macOS swap/hibernation enforcement).
- `app/static/js/modules/mode-manager/services/html-paste-sanitizer-service.js`: Client-side sanitizer for external HTML paste in edit mode (URL/style allowlist + blocked tags + image guardrails).
- `app/security/encryption.py`: Crypto facade (AES-GCM, Argon2id, versioned vault metadata + key mgmt helpers).
- `app/db`: `session.py` (begin_writer/connect_reader/read guard), `schema.py`, `notes_sql.py`, `settings_sql.py`.
- `app/static` & `app/templates`: Frontend assets and Mako templates.
- `tests/ui` + Cypress: UI E2E coverage.
- `tests/unit`: Targeted backend pytest coverage for security-critical behavior (auth vault metadata, login rate limiting, runtime hardening).

## Design
- Pattern: usecases (Cmd*) orchestrate services; services encapsulate DB work + undo logging.
- State: Notes stored as parent/prev/next pointers; decrypted cache is preloaded; sync UUIDs/locks managed in `app/services/sync.py`; active tabs/search/scroll snapshotted via `tab_state_store` so reopening the app restores the last view.
- Diff caching: Server caches each `(client, tab, search)` view and the client keeps per-tab note-hash maps so `/notes/view` diff payloads stay scoped to the active tab.
- Tab switch perf: Client can detach/cache the `#notes-container` subtree per tab and restore it instantly on return, then call `/notes/view` to reconcile small diffs.
- Client busy model: `CommandGate.run(name, asyncFn)` is the single boundary for user-initiated server calls; it is the only code allowed to flip `ModeContext.isLoading`.
- Undo boundaries: client includes an `epoch` in `undoContext` (`tab/search/epoch`); global actions bump the epoch so undo/redo cannot cross those boundaries.
- Error handling: fail-fast (internal errors crash; DB rollback triggers immediate process exit; request-validation crash toggle).
- Auth: Argon2id password verifier protecting the DEK; encrypted settings require `vault_version` + full KDF profile (`kdf_algorithm`, `kdf_memory_cost_kib`, `kdf_parallelism`); `/api2/auth/login` is rate-limited; tokens are short-lived and kept in-memory; token issuance enforces a single active session.

## Workflows
- View/diff: `POST /api2/notes/view` → `app/services/snapshot.build_view_snapshot()` → returns `snapshot{structure,notes,locks,...}` + `updateUUID`.
- Embedded references: view payload `notes[*].content` can include rendered `![[UUID]]` blocks (view mode only); host note hashes include rendered embed output.
- File attachments: `POST /api2/files/upload` stores the uploaded file in `*.files.db`, returns a UUID token, and the client inserts `![[UUID]]` into the active note (or a newly created note when none is active).
- File downloads: rendered file references in view mode call `GET /api2/files/{file_id}/download`; metadata/blob rows are decrypted on demand rather than at startup.
- File trimming: `POST /api2/files/trim-unused` deletes attachment rows no longer referenced by any note; removing refs does not auto-delete files so undo/redo remains safe until trim runs.
- Tag persistence: tags are included in `snapshot.notes[*].tags` and are saved alongside note content on `PUT /api2/notes/{id}/save`.
  - Tag bar grammar (wrappers + /* comments */): `docs/ui/tag-bar.md`.
- Tab persistence: browser boots, `tab-state-service.js` fetches `/api2/notes/tab-state`, hydrates ModeContext, throttles scroll/search changes, and POSTs back when they differ.
- Busy gating: keyboard/mouse/search/autosave actions call `CommandGate.run(...)` → server API calls → `actionRefreshAndMaybeSelect()`; background pollers skip ticks while `CommandGate.isBusy()`.
- Reference shortcut: `Cmd/Ctrl+R` copies as embedded reference (`![[UUID]]`) from the last note copied with `Cmd/Ctrl+C` (when no text selection).
- Join shortcut: `Cmd/Ctrl+J` joins the currently edited note with its next sibling by merging raw editable content and tag-bar strings; tag merge is case-insensitive dedupe (first occurrence preserved); no-op when no next sibling exists.
- Split shortcut: `Cmd/Ctrl+S` splits the currently edited note at selection/caret into sibling notes and preserves the original tag-bar string across all resulting notes; split normalization trims edge-empty nodes to avoid synthetic leading blank lines; no-op when full-note selection or end-caret would yield fewer than two non-empty segments.
- Command palette help action: `Cmd/Ctrl+/` → `Keyboard shortcuts help…` opens the shortcuts modal from palette utilities.
- External paste/drop: `keyboard-events` routes non-note clipboard HTML through `sanitizeAndInsertExternalPaste()`; clipboard and dropped image files are embedded as compressed `data:image/...` payloads (not file links).
- Backup/restore: `app/services/backup_service.py` pairs the main notes DB backup with a sibling file DB backup and rebuilds the file registry on restore.
- Backup/restore scope: backup listing/creation/restore are scoped to the active DB path; namespaces live under `~/MetaList/namespaces/<namespace>/` and back up into `~/MetaList/namespaces/<namespace>/backups/` with filenames like `<namespace>.metalist.db.<timestamp>.bak` and `<namespace>.metalist.files.db.<timestamp>.bak`.
- Note mutations: `/api2/notes/*` → `app/usecases/Cmd*` → sqlite helpers → update NoteStore + bump sync UUID.
- Undo/Redo: `/api2/notes/undo|redo` → `app/usecases/undo.py` / `app/usecases/redo.py` → `app/services/undo_state.py`.
- Auth status: `GET /api2/auth/status` is polled by the client to detect session/auth changes.
- Startup: `main.py` can select a namespaced DB (`METALIST_NAMESPACE` or `--namespace`) before importing `app.main`; `app/main.py` then initializes schema + settings for that selected DB. If encryption is disabled, it populates the content cache and hydrates NoteStore before enabling the read guard. If encryption is enabled, hydration is deferred until login (`POST /api2/auth/hydrate`) and the UI shows a first-load progress state.
- Legacy import: `convert-from-legacy.py` is a destructive fresh-import path that can prompt for password setup and writes the same Argon2id vault metadata as runtime auth.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install
python main.py
```

## Quick Ref
- Config: `app/config.py` (DB path, API prefix, crash-on-fail, token expiry, Argon2id costs).
- Namespace DBs: omitted namespace means `default`, so the default DB is `~/MetaList/namespaces/default/default.metalist.db`; `--namespace work` / `METALIST_NAMESPACE=work` uses `~/MetaList/namespaces/work/work.metalist.db`, and the related files DB derives as `namespaces/work/work.metalist.files.db`.
- Frontend paste config: `app/static/js/modules/config.js` (`CONFIG.PASTE.MAX_DATA_IMAGE_BYTES`).
- Frontend split shortcut: `app/static/js/modules/mode-manager/actions/note-actions.js` (`splitCurrentNoteFromSelection`) + `app/static/js/modules/mode-manager/events/keyboard-events.js` (`Cmd/Ctrl+S` binding).
- Frontend join shortcut: `app/static/js/modules/mode-manager/actions/note-actions.js` (`joinCurrentNoteWithNextSibling`) + `app/static/js/modules/mode-manager/events/keyboard-events.js` (`Cmd/Ctrl+J` binding).
- Store: `app/services/note_store.py` (in-memory note graph + ordering).
- File store: `app/services/file_storage.py` + `app/services/file_registry.py`.
- Snapshots: `app/services/snapshot.py` (view snapshot builder).
- Security: `app/security/encryption.py` (encrypt/decrypt + key derivation).
- Runtime hardening: `app/services/runtime_hardening.py` (core-dump disable by default; optional strict macOS swap/hibernation checks can fail startup when enabled).
- DB guard: `app/db/session.py` (begin_writer/connect_reader + post-startup SELECT guard).
- Undo: `app/services/undo_state.py`.
- Ontology rules (v1): `app/services/tag_ontology.py` + `app/services/ontology_rules_store.py` (SQLite-backed, cached in memory).
  - API/UI: `app/api/routes/ontology.py` + `app/static/js/modules/modals/ontology-modal.js`.

## Layer Boundaries
- `app/api/`: HTTP delivery only. FastAPI/Pydantic imports ok. Depends on `app/usecases/`.
- `app/usecases/`: Transport-agnostic Cmd* orchestration. No FastAPI imports. Depends on `app/services/`.
- `app/services/`: Reusable capabilities (DB/cache/auth/note_store/integrity). No APIRouter or route wiring.
- `app/presentation/`: Templates + renderers for server-side views.

## Gotchas / Open Issues
- Removing the `app/services/store.py` adapter and calling `NoteStore` directly from all usecases still exposes referential integrity issues in some undo flows (delete/move). Adapter remains; revisit with tighter invariants + targeted tests.
- Search is server-side + indexed: `app/services/search_index.py` (tag postings + trigram postings over `strip_html(content)`), used by `app/services/snapshot.py` to filter `/api2/notes/view`.
  - Query terms: unquoted tokens are tag terms; quoted strings are text terms (see `docs/ui/search-syntax.md` + `docs/ui/search-semantics.md`).
  - Views remain windowed (roots chunked; infinite scroll extends as needed).
