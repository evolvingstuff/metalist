# AI-SUMMARY

## Project: MetaList
- Single-user FastAPI app for hierarchical notes with SSR + a diff-based `POST /api2/notes/view`.

## Architecture
- Entry: `main.py` - runs Uvicorn (`app.main:app`) with access-log noise filtering.
- `app/main.py`: FastAPI wiring, middleware, startup bootstrapping, SSR templates.
- `app/api/routes`: JSON routers mounted under `API_PREFIX` (default `/api2`).
  - `app/api/routes/notes.py`
  - `app/api/routes/auth.py`
  - `app/api/routes/memory.py`
- `app/api/middleware/auth.py`: Auth middleware gating routes when a password exists.
- `app/usecases`: Cmd* application commands (transport-agnostic orchestration).
- `app/services`: Auth, tokens, cache, sync, undo, integrity, note store, snapshots, tab state cache.
- `app/services/note_store.py`: Canonical in-memory store for decrypted notes + parent/prev/next links.
- Notes schema: `notes.content` + `notes.tags` are persisted; tags are a space-separated string.
- `app/services/snapshot.py`: Builds the view snapshot used by `/api2/notes/view`.
- `app/services/content_formatting.py`: Applies view-only meta-tag formatting (`@monospace`, `@red`) with optional wrapper scoping.
- `app/services/tab_state.py`: Tracks `(client, tab)` search + scroll metadata used by the UI between reloads.
- `app/security/encryption.py`: Crypto facade (AES-GCM, PBKDF2, key mgmt helpers).
- `app/db`: `session.py` (begin_writer/connect_reader/read guard), `schema.py`, `notes_sql.py`, `settings_sql.py`.
- `app/static` & `app/templates`: Frontend assets and Mako templates.
- `tests/ui` + Cypress: UI E2E coverage; backend pytest suites are effectively retired.

## Design
- Pattern: usecases (Cmd*) orchestrate services; services encapsulate DB work + undo logging.
- State: Notes stored as parent/prev/next pointers; decrypted cache is preloaded; sync UUIDs/locks managed in `app/services/sync.py`; active tabs/search/scroll snapshotted via `tab_state_store` so reopening the app restores the last view.
- Diff caching: Server caches each `(client, tab, search)` view and the client keeps per-tab note-hash maps so `/notes/view` diff payloads stay scoped to the active tab.
- Tab switch perf: Client can detach/cache the `#notes-container` subtree per tab and restore it instantly on return, then call `/notes/view` to reconcile small diffs.
- Client busy model: `CommandGate.run(name, asyncFn)` is the single boundary for user-initiated server calls; it is the only code allowed to flip `ModeContext.isLoading`.
- Undo boundaries: client includes an `epoch` in `undoContext` (`tab/search/epoch`); global actions bump the epoch so undo/redo cannot cross those boundaries.
- Error handling: fail-fast (internal errors crash; DB rollback triggers immediate process exit; request-validation crash toggle).
- Auth: PBKDF2 password verifier protecting the DEK; tokens are short-lived and kept in-memory; token issuance enforces a single active session.

## Workflows
- View/diff: `POST /api2/notes/view` → `app/services/snapshot.build_view_snapshot()` → returns `snapshot{structure,notes,locks,...}` + `updateUUID`.
- Tag persistence: tags are included in `snapshot.notes[*].tags` and are saved alongside note content on `PUT /api2/notes/{id}/save`.
  - Tag bar grammar (wrappers + /* comments */): `docs/ui/tag-bar.md`.
- Tab persistence: browser boots, `tab-state-service.js` fetches `/api2/notes/tab-state`, hydrates ModeContext, throttles scroll/search changes, and POSTs back when they differ.
- Busy gating: keyboard/mouse/search/autosave actions call `CommandGate.run(...)` → server API calls → `actionRefreshAndMaybeSelect()`; background pollers skip ticks while `CommandGate.isBusy()`.
- Note mutations: `/api2/notes/*` → `app/usecases/Cmd*` → sqlite helpers → update NoteStore + bump sync UUID.
- Undo/Redo: `/api2/notes/undo|redo` → `app/usecases/undo.py` / `app/usecases/redo.py` → `app/services/undo_state.py`.
- Auth status: `GET /api2/auth/status` is polled by the client to detect session/auth changes.
- Startup: `app/main.py` initializes schema, loads settings, populates content cache, hydrates NoteStore, then enables the read guard.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install
python main.py
```

## Quick Ref
- Config: `app/config.py` (DB path, API prefix, crash-on-fail, token expiry, PBKDF2 iterations).
- Store: `app/services/note_store.py` (in-memory note graph + ordering).
- Snapshots: `app/services/snapshot.py` (view snapshot builder).
- Security: `app/security/encryption.py` (encrypt/decrypt + key derivation).
- DB guard: `app/db/session.py` (begin_writer/connect_reader + post-startup SELECT guard).
- Undo: `app/services/undo_state.py`.

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
