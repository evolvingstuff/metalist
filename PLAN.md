# PLAN: Move Search History Into Main Namespace DB

## Goal
Store search history in the main namespace database instead of a sibling `*.search-history.db`, while preserving MetaList's memory-first runtime contract.

## Confirmed Decisions
- Search history starts empty after this change; old `*.search-history.db` data is ignored.
- Existing sidecar search-history files are not deleted automatically.
- Files remain in the sibling `*.files.db` because blobs are intentionally not hydrated at startup.
- Search history must follow the normal namespace-state pattern: load into server memory, then write-through to SQLite on updates; no runtime DB reads after startup/hydration.
- Search-history payload fields remain encrypted at rest when namespace encryption is enabled.
- Add an explicit maximum of 500 search-history rows.
- Normalize query identity by sorting and deduping positive tag terms, so `journal exercise` and `exercise journal` share one stored history row.

## Implementation Steps
1. Move schema ownership into the main DB
   - Add `search_interaction_history` table and score index to `app/db/schema.py`.
   - Keep or adapt `app/db/search_history_sql.py` as the SQL helper for this table.
   - Stop relying on `app/db/search_history_session.py` for runtime storage.

2. Introduce memory-first search history state
   - Add a service-owned in-memory cache/store for search-history rows.
   - Load all search-history rows during startup and post-login hydration.
   - Keep suggestion reads and ranking fully in memory.
   - On each credited interaction, update the in-memory store first, then write the changed rows/deletes to the main DB.

3. Update normalization and retention
   - Continue ignoring blank, text-only, UUID-only, negative-only, and zero-result searches.
   - Normalize positive tag terms by case-insensitive sort plus deterministic tie-breaker.
   - Deduplicate repeated terms within the same query.
   - Preserve typed/display spelling in stored payload where practical.
   - Enforce the 500-row cap after decay/prune/update by deleting the lowest-ranked excess rows.

4. Preserve encryption behavior
   - Keep query key, root tag, and tags JSON encrypted at rest when a namespace password is enabled.
   - Keep operational metadata such as query hash, score, and timestamps plaintext.
   - Update password set/remove flows so search-history rewrites operate on the main DB and in-memory store inside the existing password-transition flow.

5. Remove search-history sidecar backup behavior
   - New backups include notes DB plus files DB only.
   - Old archive backups that contain a search-history sidecar should ignore that member.
   - Old legacy `.search-history.db.bak` sidecars should be ignored on restore.
   - Backup cleanup can still delete matching legacy search-history sidecars when deleting old legacy primary backups.

6. Update tests
   - Search-history unit tests should use the main in-memory DB path/session.
   - Add/adjust tests for sorted/deduped normalized query keys.
   - Add tests for the 500-row retention cap.
   - Update auth password-transition tests for main-DB search-history rows.
   - Update backup tests so search-history sidecars are no longer included/restored.

7. Update docs
   - Update `docs/AI-SUMMARY.md`.
   - Update backup/search-history documentation that mentions `*.search-history.db`.
   - Clarify that files are the only sibling DB for large blob storage.

## Verification
- Run focused tests:
  - `./.venv/bin/pytest tests/unit/test_search_history.py`
  - `./.venv/bin/pytest tests/unit/test_auth_vault_metadata.py`
  - `./.venv/bin/pytest tests/unit/test_backup_service.py`
- Run broader relevant tests if focused tests uncover cross-module impact.

## Open Risks
- Password-transition flows currently rewrite search history through the sidecar session; moving that into the main DB must avoid nested writer/locking issues.
- Startup/hydration must load search history only after the active DEK is available for encrypted namespaces.
- Retention cap enforcement must be deterministic so tests and suggestion ranking remain stable.
