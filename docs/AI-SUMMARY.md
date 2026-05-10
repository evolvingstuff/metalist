# AI-SUMMARY

## Project: MetaList
- Single-user FastAPI app for hierarchical notes with SSR + a diff-based `POST /api2/notes/view`.

## Architecture
- Entry: installed CLI `metalist` → `main.py:main()`; source-checkout `python main.py` still works, but plain `python main.py` now bootstraps every known namespace from the current checkout and exits after printing the per-namespace URLs.
- Packaging: `pyproject.toml` packages the `app/` package plus templates/static assets; installed helper commands include `metalist-mcp`, `convert-from-legacy.py`, and `generate-lan-cert.sh`.
- Release workflow: `.github/workflows/publish-pypi.yml` builds the package and publishes it to PyPI via GitHub Trusted Publishing on `v*` tags or manual dispatch.
- Prelaunch gate: `main.py` runs Python + JS startup sanity checks once in the parent process before any namespace restart/launch work. Python rules live in `app/startup_sanity.py`; JS rules live in `app/startup_js_sanity.py`; shared constants live in `app/startup_sanity_config.py`.
- Startup bootstrap: `main.py` resolves `--namespace`, positional namespace shorthand (`metalist cla` or `python main.py cla`), `--port`, `--https-port`, and `--mcp-port` before importing `app.main`, so explicit single-namespace launches still expose the right DB path and listener ports at import time.
- Namespace launch profiles: `app/server_runtime.py` stores remembered per-namespace HTTP / HTTPS / MCP sidecar ports in `~/MetaList/namespaces.db`.
- Namespace switching/launching: `app/services/namespace_switcher.py` lists known namespaces, suggests conflict-free ports, restarts already-running target namespaces so they pick up current code, relaunches the recorded entrypoint (installed CLI or source script), auto-evicts stale listeners on the assigned ports, and writes child logs under `~/MetaList/logs/`.
- Child entrypoint: `serve_namespace.py` is the namespace-serving source entrypoint so child processes do not re-enter the parent orchestration path in `main.py`.
- `app/main.py`: FastAPI wiring, middleware, startup bootstrapping, SSR templates.
- `app/static/js/main.js`: Browser bootstrap; awaits `Auth.init()`, `ModeManager.init()`, and `CommandPalette.init()` before revealing the app, and sets `document.body.dataset.appReady` for deterministic Cypress startup waits.
- Startup intro gate: `app/templates/index.html` + `app/static/js/modules/auth.js` can show a login/startup MP4 before revealing login or the app; the login card now shows a single namespace-aware title (`MetaList` for `default`, `MetaList [work]` otherwise) plus a bottom namespace picker that can redirect before authentication; this is controlled by `STARTUP_ANIMATION_ENABLED` and defaults off.
- `app/api/routes`: JSON routers mounted under `API_PREFIX` (default `/api2`).
  - `app/api/routes/notes.py`
  - `app/api/routes/auth.py`
  - `app/api/routes/memory.py`
  - `app/api/routes/files.py`
- `app/api/middleware/auth.py`: Auth middleware gating routes when a password exists.
- `app/usecases`: Cmd* application commands (transport-agnostic orchestration).
- `app/services`: Auth, tokens, cache, sync, undo, integrity, note store, file storage, snapshots, tab state cache, session-timeout settings.
- `app/services/client_state_service.py`: Stores namespace-scoped command-palette preferences/usage in `app_settings` so UI preferences travel with the namespace instead of the browser.
- `app/services/note_store.py`: Canonical in-memory store for decrypted notes + parent/prev/next links.
- `app/services/file_storage.py`: Stores file attachments in a sibling `*.files.db` SQLite database; uses plaintext rows when the app has no password and encrypted metadata/blob rows when the app is in encrypted mode.
- `app/services/search_history.py`: Stores interacted search histories in a sibling `*.search-history.db` SQLite database; successful non-empty searches and newly added non-meta note tags feed recent-tag activity; blank-search and first-tag-prefix suggestions can reserve the top 3 slots for the highest-scoring recent matching tags, case-equivalent tags are collapsed to the most-used spelling, and stored query/tag payloads encrypt at rest when the namespace is password-protected.
- `app/services/file_registry.py`: In-memory registry of valid file UUIDs only; startup bootstraps this without hydrating file rows/blobs.
- `app/services/backup_settings_service.py`: Stores the configured backup folder, selected namespaces, and retention count in the namespace DB; when namespace encryption is enabled, that payload is encrypted at rest too.
- Notes schema: `notes.content` + `notes.tags` are persisted; tags are a space-separated string.
- `app/services/snapshot.py`: Builds the view snapshot used by `/api2/notes/view`.
- `app/services/content_formatting.py`: Applies view-only meta-tag formatting (`@monospace`, `@red`) with optional wrapper scoping, auto-links bare `http(s)` URLs in rendered notes, and normalizes rendered anchors to open in a new tab.
- `app/services/tag_term_matching.py`: Shared helper for connector-aware, punctuation-tolerant tag suggestion matching/ranking (`-`, `_`, `.`, `/`) used by search suggestions and tag suggestions.
- `app/services/embedded_references.py`: Resolves note/file UUID references in view mode (embedded notes, note previews, file cards, missing/cycle markers).
- `app/services/tab_state.py`: Stores namespace-scoped tab workspace state (`activeTabId`, `tabOrder`, per-tab search/scroll/sort metadata) in the main SQLite DB; rows stay plaintext without a password and are DEK-encrypted at rest when the namespace is password-protected.
- `app/services/login_rate_limit.py`: In-memory login attempt throttling for `/api2/auth/login`.
- `app/services/runtime_hardening.py`: Startup hardening (disable core dumps; macOS swap/hibernation enforcement).
- `app/static/js/modules/mode-manager/services/html-paste-sanitizer-service.js`: Client-side sanitizer for external HTML paste in edit mode (URL/style allowlist + blocked tags + image guardrails).
- `app/security/encryption.py`: Crypto facade (AES-GCM, Argon2id, versioned vault metadata + key mgmt helpers).
- `app/db`: `session.py` (begin_writer/connect_reader/read guard), `schema.py`, `notes_sql.py`, `settings_sql.py`.
- `app/static` & `app/templates`: Frontend assets and Mako templates.
- `tests/unit`: targeted pytest coverage plus Node `.mjs` unit tests for shared frontend logic; there is no current Cypress harness.

## Design
- Pattern: usecases (Cmd*) orchestrate services; services encapsulate DB work + undo logging.
- State: Notes stored as parent/prev/next pointers; decrypted cache is preloaded; sync UUIDs/locks managed in `app/services/sync.py`; active tabs/search/scroll are snapshotted via `tab_state_store` into the namespace DB so reopening the app or restarting the server restores the last view; command-palette prefs/usage are persisted per namespace in `app_settings` instead of browser `localStorage`.
- Root sort modes: per-tab server-owned `sortMode` (`normal`, `created`, `updated`) lives in `app/services/tab_state.py`; datetime modes sort/window root notes by the newest matching timestamp anywhere in each root subtree, while the client renders day separators from `snapshot.rootSortBuckets`.
- Mutation safety: mutating FastAPI routes are expected to carry `@transactional_route`; startup sanity enforces the decorator ordering in source, and request-scoped write sessions commit once at the end of the wrapped request path.
- Diff caching: Server caches each `(client, tab, search)` view and the client keeps per-tab note-hash maps so `/notes/view` diff payloads stay scoped to the active tab.
- Tab switch perf: Client can detach/cache the `#notes-container` subtree per tab and restore it instantly on return, then call `/notes/view` to reconcile small diffs.
- Client busy model: `CommandGate.run(name, asyncFn)` is the single boundary for user-initiated server calls; it is the only code allowed to flip `ModeContext.isLoading`.
- Undo boundaries: client includes an `epoch` in `undoContext` (`tab/search/epoch`); global actions bump the epoch so undo/redo cannot cross those boundaries. Sort-mode changes are one of those global boundaries and blank undo/redo for the active tab context.
- Error handling: fail-fast (internal errors crash; DB rollback triggers immediate process exit; request-validation crash toggle).
- Auth: Argon2id password verifier protecting the DEK; encrypted settings require `vault_version` + full KDF profile (`kdf_algorithm`, `kdf_memory_cost_kib`, `kdf_parallelism`); `/api2/auth/login` is rate-limited; pre-login namespace selection uses `GET /api2/auth/login-namespaces` + `POST /api2/auth/login-namespaces/open` to redirect into another namespace without widening the authenticated namespace APIs; tokens are short-lived and kept in-memory on the server, but the browser now carries them via an HttpOnly `metalist_auth` cookie instead of `localStorage`; token issuance enforces a single active session.

## Workflows
- View/diff: `POST /api2/notes/view` → `app/services/snapshot.build_view_snapshot()` → returns `snapshot{structure,notes,locks,...}` + `updateUUID`.
- Root sorting: `POST /api2/notes/tab-state/sort-mode` updates per-tab sort state; subsequent `POST /api2/notes/view` responses echo `sortMode` and `rootSortBuckets`, and the client inserts ephemeral date separators between visible roots for datetime modes.
- Embedded references: view payload `notes[*].content` can include rendered `![[UUID]]` blocks (view mode only); host note hashes include rendered embed output.
- File attachments: `POST /api2/files/upload` stores the uploaded file in `*.files.db`, returns a UUID token, and the client inserts `![[UUID]]` into the active note (or a newly created note when none is active).
- File downloads: rendered file references in view mode call `GET /api2/files/{file_id}/download`; metadata/blob rows are decrypted on demand rather than at startup.
- File trimming: `POST /api2/files/trim-unused` deletes attachment rows no longer referenced by any note; removing refs does not auto-delete files so undo/redo remains safe until trim runs.
- Tag persistence: tags are included in `snapshot.notes[*].tags` and are saved alongside note content on `PUT /api2/notes/{id}/save`.
  - Tag bar grammar (wrappers + /* comments */): `docs/ui/tag-bar.md`.
- Suggestion behavior: search-bar and tag-bar suggestions are segment-aware for connector-separated tags, collapse case-equivalent tags to one displayed spelling, but actual search filtering remains exact on effective tag terms.
- Tag suggestion ranking: tag-bar suggestions interleave top literal content hits with top direct co-occurrence hits from the current explicit tags, suppress blank-prefix content variants already covered by an explicit/inherited tag segment, treat connector-separated partials literally (`Y-Z` before `X-Y-Z` for `Y Z`), and prefer structured/longer entity hits like `CookUnity` over shorter plain-word hits like `meal` when content-hit strength otherwise ties. Server caps are `MAX_SEARCH_SUGGESTIONS` and `MAX_TAG_SUGGESTIONS`.
- Tab persistence: browser boots, `tab-state-service.js` fetches `/api2/notes/tab-state`, hydrates ModeContext, throttles scroll/search changes, and POSTs back when they differ; the server persists that snapshot per namespace in SQLite and rewrites it between plaintext/encrypted storage when password protection is toggled.
- Client-state persistence: browser boots, `auth.js` reads theme from `/api2/auth/status`, `command-palette-controller.js` loads `/api2/auth/client-state`, migrates any legacy browser `localStorage` palette data once, and persists future palette preference/usage updates back into the namespace DB.
- Busy gating: keyboard/mouse/search/autosave actions call `CommandGate.run(...)` → server API calls → `actionRefreshAndMaybeSelect()`; background pollers skip ticks while `CommandGate.isBusy()`.
- Edit focus styling: `app/static/css/main.css` uses `#notes-container:has(.note.editing)` to slightly blur non-editing note content/toggles outside the edited note subtree, including ancestor content, while keeping the edited note and its children sharp.
- Test harness boundary: `POST /api2/test/reset` clears DB/search-history/cache/tab/auth/sync state, and `app/static/js/main.js` exposes `body[data-app-ready="true"]` after `Auth.init()`, `ModeManager.init()`, and `CommandPalette.init()` complete.
- Reference shortcut: `Cmd/Ctrl+R` copies as embedded reference (`![[UUID]]`) from the last note copied with `Cmd/Ctrl+C` (when no text selection).
- Note clipboard: `Cmd/Ctrl+C` with no text selection stores the note subtree server-side and writes promised `text/html` + tab-indented `text/plain` to the system clipboard; `Cmd/Ctrl+V` into an empty target note replaces that target, preserving/merging its context tags with copied root tags via case-insensitive dedupe.
- Join shortcut: `Cmd/Ctrl+J` joins the currently edited note with its next sibling by merging raw editable content and tag-bar strings; tag merge is case-insensitive dedupe (first occurrence preserved); no-op when no next sibling exists.
- Split shortcut: `Cmd/Ctrl+S` splits the currently edited note at selection/caret into sibling notes and preserves the original tag-bar string across all resulting notes; split normalization trims edge-empty nodes to avoid synthetic leading blank lines; no-op when full-note selection or end-caret would yield fewer than two non-empty segments.
- Move-to-top shortcut: `Cmd/Ctrl+Shift+Up` is server-driven; a selected root note moves to the top of the current root view (including filtered/search views), while a child note moves to the top of its sibling list.
- Command palette help action: `Cmd/Ctrl+/` → `Keyboard shortcuts help…` opens the shortcuts modal from palette utilities.
- Login screen namespace switcher: the bottom login picker lists plain namespace names (`default`, `cla`, etc.), immediately redirects through the login-only namespace-open flow, and lands directly in passwordless namespaces because the destination page auto-claims a passwordless session on load.
- Namespace switcher: `Cmd/Ctrl+/` → `Switch or create namespace…` opens a modal backed by `GET /api2/auth/namespaces` and `POST /api2/auth/namespaces/open`; it reuses saved launch profiles for existing namespaces, suggests next-free ports for new namespaces, restarts already-running target namespaces from the current code, and otherwise waits for the freshly spawned instance before returning its URL.
- External paste/drop: `keyboard-events` routes non-note clipboard HTML through `sanitizeAndInsertExternalPaste()`; clipboard image pixels still embed as compressed `data:image/...`, while named pasted/dropped image files can either embed inline or be saved as file attachments via a choice modal.
- View-mode links: bare pasted `http(s)` text becomes clickable in rendered note HTML, and rendered non-hash anchors open in a new browser tab instead of replacing the MetaList tab.
- Image file refs in view mode: embedded image attachments render as authenticated previews with a `download image` control; collapsed notes reduce them to a compact thumbnail.
- Alphabetize root notes: `Cmd/Ctrl+/` → `Alphabetize root notes A-Z/Z-A (current view)…` opens an app-styled confirmation, then permanently rewrites only root-note order within the active search context by root content; Cmd+Z cannot undo it because the command bumps the undo epoch and the server clears that undo context.
- Backup/restore: `app/services/backup_service.py` snapshots the notes DB plus sibling file/search-history DBs into one versioned `.tar.gz` archive, validates manifest checksums/format on restore, rebuilds the file registry afterward, and still restores legacy `.bak` snapshots for compatibility.
- Backup settings: `GET/PUT /api2/backup/settings` stores the configured folder path, selected namespaces, and per-namespace retention count for manual runs.
- Backup run: `POST /api2/backup/run` creates one archive per selected namespace, writes them all into the configured folder, and reports one result row per namespace in the result modal.
- Backup/restore scope: backup listing/creation/restore are scoped to the active DB path; namespaces live under `~/MetaList/namespaces/<namespace>/` and back up into `~/MetaList/namespaces/<namespace>/backups/` with filenames like `<namespace>-<timestamp>.metalist-backup.tar.gz`.
- Note mutations: `/api2/notes/*` → `app/usecases/Cmd*` → sqlite helpers → update NoteStore + bump sync UUID.
- Undo/Redo: `/api2/notes/undo|redo` → `app/usecases/undo.py` / `app/usecases/redo.py` → `app/services/undo_state.py`.
- Auth status: `GET /api2/auth/status` is polled by the client to detect session/auth changes.
- Startup: explicit single-namespace `main.py` runs can select a namespaced DB (`METALIST_NAMESPACE` or `--namespace`) before importing `app.main`; `app/main.py` then initializes schema + settings for that selected DB. If encryption is disabled, it populates the content cache and hydrates NoteStore before enabling the read guard. If encryption is enabled, hydration is deferred until login (`POST /api2/auth/hydrate`) and the UI shows a first-load progress state. Plain source-checkout `python main.py` uses the namespace switcher to restart/start every known namespace instead of running just `default` in-process.
- Legacy import: `convert-from-legacy.py` is a destructive fresh-import path that prompts for namespace/ports when omitted, persists that namespace launch profile, can prompt for password setup, and writes the same Argon2id vault metadata as runtime auth.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install metalist    # published install
# or from source:
# pip install .
# pip install -e .[dev] for local development
# npm install            # only for Node-based JS unit tests / Mermaid rendering
metalist
```

## Quick Ref
- Config: `app/config.py` (DB path, API prefix, crash-on-fail, default token expiry fallback, Argon2id costs). Runtime idle timeout is namespace-scoped in `app_settings`, editable from the command palette, and can be disabled.
- Startup intro toggle: `STARTUP_ANIMATION_ENABLED=1` enables the login/startup MP4 gate; omitted/off skips the intro and uses the legacy immediate app/login reveal.
- Namespace DBs: omitted namespace on a single-namespace launch means `default`, so the default DB is `~/MetaList/namespaces/default/default.metalist.db`; `--namespace work`, `metalist work`, or `METALIST_NAMESPACE=work` uses `~/MetaList/namespaces/work/work.metalist.db`, and the related files DB derives as `namespaces/work/work.metalist.files.db`. Plain source-checkout `python main.py` bootstraps all known namespaces instead of selecting only `default`.
- Default TLS paths: `~/MetaList/certs/metalist-cert.pem` + `~/MetaList/certs/metalist-key.pem`; `main.py` auto-generates that self-signed pair on first non-test startup unless `METALIST_AUTO_GENERATE_TLS=0`, and `generate-lan-cert.sh` remains an optional manual regeneration path.
- Launch profile precedence: CLI flags override env vars, which override `~/MetaList/namespaces.db`, which overrides built-in defaults.
- Namespace UI/runtime bridge: `app/api/routes/auth.py` now exposes login-screen namespace list/open endpoints plus the authenticated namespace catalog + open/launch endpoints; `app/static/js/modules/login-namespace-picker.js` formats the login title/picker state and `app/static/js/modules/modals/namespace-switcher-modal.js` remains the command-palette modal.
- Frontend paste config: `app/static/js/modules/config.js` (`CONFIG.PASTE.MAX_DATA_IMAGE_BYTES`).
- Frontend split shortcut: `app/static/js/modules/mode-manager/actions/note-actions.js` (`splitCurrentNoteFromSelection`) + `app/static/js/modules/mode-manager/events/keyboard-events.js` (`Cmd/Ctrl+S` binding).
- Frontend join shortcut: `app/static/js/modules/mode-manager/actions/note-actions.js` (`joinCurrentNoteWithNextSibling`) + `app/static/js/modules/mode-manager/events/keyboard-events.js` (`Cmd/Ctrl+J` binding).
- Store: `app/services/note_store.py` (in-memory note graph + ordering).
- File store: `app/services/file_storage.py` + `app/services/file_registry.py`.
- Search history store: `app/services/search_history.py` + `app/db/search_history_session.py`.
- Snapshots: `app/services/snapshot.py` (view snapshot builder).
- Security: `app/security/encryption.py` (encrypt/decrypt + key derivation).
- Runtime hardening: `app/services/runtime_hardening.py` (core-dump disable by default; optional strict macOS swap/hibernation checks can fail startup when enabled).
- Startup sanity: `main._run_startup_sanity_gates(...)` runs Python AST/transaction checks plus the Python tree-sitter JS sanity pass; startup sanity no longer depends on the old `sanitycheck/` folder or Node.
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
- Root sorting helper: `app/services/root_sorting.py` centralizes sort-mode normalization, subtree-max root timestamps, server-side root ordering, and date-bucket metadata for the client.
