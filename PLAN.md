# PLAN: Move Namespace Launch Profiles Into Namespace DBs

## Goal
Remove the global `~/MetaList/namespaces.db` launch-profile registry. Store each namespace's launch profile as plaintext operational metadata inside that namespace's main `*.metalist.db`, while keeping the existing branch focused on database cleanup.

## Confirmed Decisions
- Stay on the current feature branch.
- Namespace folders are the source of truth for namespace existence.
- Each namespace's HTTP / HTTPS / MCP launch ports live in that namespace's own main DB.
- Launch profile fields are plaintext even when namespace content is encrypted.
- Parent startup scans `~/MetaList/namespaces/` once, reads each namespace DB's launch profile, and keeps the catalog in memory.
- Runtime reads from a global registry DB are removed because there is no registry DB.
- If a namespace folder exists but its main DB is missing/corrupt/unreadable, fail loudly.
- Same-name restore is the normal restore path: restoring `foo` into existing `foo` replaces that namespace's app data/files and may happen while `foo` is running.
- Restoring/importing backup namespace `foo` as a different namespace name should warn/fail only if the target name already exists.
- Port conflicts should be checked during restore/import when creating a different target namespace or when applying restored launch-profile metadata to a new namespace.
- Files remain in `*.files.db`; this change is only about `namespaces.db` launch metadata.

## Implementation Steps
1. Add launch-profile storage to main schema
   - Add a table such as `namespace_launch_profile` to `app/db/schema.py`.
   - Store `namespace`, `port`, `https_port`, `mcp_port`, `created_at`, and `updated_at`.
   - Do not encrypt these fields.
   - Add SQL helpers for fetch/upsert/delete if helpful.

2. Replace `~/MetaList/namespaces.db` runtime APIs
   - Refactor `app/server_runtime.py` functions:
     - `load_namespace_launch_profile`
     - `load_all_namespace_launch_profiles`
     - `save_namespace_launch_profile`
     - `delete_namespace_launch_profile`
     - `resolve_namespace_launch_defaults`
   - Make them operate on namespace DBs under `~/MetaList/namespaces/<ns>/<ns>.metalist.db`.
   - Remove or deprecate `resolve_namespace_registry_path`.
   - Keep validation strict and fail loudly on malformed/missing DB state.

3. Startup discovery
   - Scan the namespace directory once at parent startup or at namespace-catalog construction.
   - Include `default` even if no folder exists yet, creating/initializing its DB when needed.
   - Read launch profiles from each namespace DB and cache the result in memory where appropriate.
   - Ensure directory names, DB filenames, and stored namespace names agree.

4. Creation and port management
   - Namespace creation should create the namespace folder and main DB first, then save its launch profile into that DB.
   - Manage Namespace Ports should read/write profiles through the namespace DBs.
   - Batch validation should still catch duplicate requested ports, conflicts with saved profiles, and conflicts with running/current processes.

5. Backup and restore semantics
   - Backups automatically carry launch-profile metadata because it is inside the main namespace DB.
   - Restore into the same namespace name should restore app data/files normally and keep or reconcile local runtime state without treating name existence as an error.
   - Import/restore under a different namespace name should fail or require explicit confirmation if that target namespace already exists.
   - When importing under a different name, rewrite the stored namespace name in the restored launch-profile row and resolve port conflicts before launch.
   - If restoring into the same namespace while it is running, use the existing maintenance/reset/reload path.

6. Migration and compatibility
   - On first startup after this change, if old `~/MetaList/namespaces.db` exists, read profiles from it and copy them into each namespace DB when that DB exists or is created.
   - Do not require the old registry after migration.
   - Do not delete `namespaces.db` automatically in the first implementation; ignore it after migration.
   - If both old registry and namespace DB profile exist, namespace DB wins unless the namespace DB profile is missing.

7. Delete namespace behavior
   - Deleting a namespace removes its namespace directory, including the profile because it is in the namespace DB.
   - Remove the separate registry-profile delete from the worker path.
   - Update deletion UI/docs copy that mentions saved profiles/ports.

8. Tests
   - Update `tests/unit/test_server_runtime.py` for DB-backed launch profiles.
   - Update `tests/unit/test_namespace_switcher.py` for catalog scan + DB-backed save/read.
   - Update main entrypoint tests that assert saved profile behavior.
   - Add migration tests from old `namespaces.db` into namespace DB profile rows.
   - Add restore/import tests for:
     - same-name restore allowed
     - different-name conflict rejected
     - different-name import rewrites profile namespace and resolves/checks ports
   - Keep full pytest passing.

9. Docs
   - Update `docs/AI-SUMMARY.md`.
   - Update README namespace setup/launch sections.
   - Update MCP/security/electron/command-palette docs that mention `~/MetaList/namespaces.db`.
   - Clarify persistent DB model:
     - main namespace DB: notes, app state, reminders, search history, launch profile
     - files DB: large file blobs
     - no global namespace registry DB

## Verification
- Focused tests:
  - `./.venv/bin/pytest tests/unit/test_server_runtime.py`
  - `./.venv/bin/pytest tests/unit/test_namespace_switcher.py`
  - `./.venv/bin/pytest tests/unit/test_main_entrypoint.py`
  - `./.venv/bin/pytest tests/unit/test_backup_service.py tests/unit/test_backups_route.py`
- Startup sanity:
  - `./.venv/bin/python -c "from pathlib import Path; from app.startup_sanity import assert_startup_sanity; assert_startup_sanity(Path('.').resolve())"`
- Full test suite:
  - `./.venv/bin/pytest`

## Open Risks
- Parent orchestration imports `app.server_runtime` before namespace-specific app startup, so DB-backed profile reads must not depend on an active namespace import context.
- Old registry migration must not silently overwrite newer namespace-DB profile rows.
- Restore/import needs a clear API distinction between same-name restore and different-name import/clone.
- Existing UI copy and tests assume one central "saved ports" table; implementation should preserve the UX while changing the backing store.
