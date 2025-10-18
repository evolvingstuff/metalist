# DB Cache Corruption Investigation

## Incident Snapshot
- **Endpoint:** `/api/notes/view`
- **Crash signature:** `CACHE CORRUPTION: Note f22c2495-c1e6-4c85-9e55-6b8ee9496e96 not found in cache`
- **Trigger:** Server startup followed by rendering notes view
- **Observed effect:** FastAPI middleware aborted request because `build_note_tree` could not locate cached plaintext for note `f22c2495-c1e6-4c85-9e55-6b8ee9496e96`.

## Data Inspection
- Ran `.venv/bin/python db_analysis.py --db notes.db --note-id f22c2495-c1e6-4c85-9e55-6b8ee9496e96`.
- **Totals:** 22 notes, 10 root-level, encryption metadata absent for every note.
- **Target note:**
  - `content=""` (empty string)
  - `encryption_nonce NULL`, `encryption_tag NULL`
  - Linked-list pointers valid (`prev_id=None`, `next_id=a7d0f273-...`).
- Linked-list validation passed for every parent scope; no orphaned pointers detected.
- Conclusion: Database rows were internally consistent; only anomaly was the empty plaintext.

## Code Path Review
1. **Cache population** (`app/services/content_cache.py:91-131`):
   - Previously skipped any note where `if note.content:` evaluated falsy.
   - Empty string values were ignored, resulting in no cache entry even though the note exists in the DB.
2. **Renderer invariant** (`app/render/note_renderer.py:262-268`):
   - Expects `get_cached_content(note.id)` to return a non-`None` value for every note retrieved from the database.
   - Missing cache entry triggers `RuntimeError` labelled as cache corruption.
3. **Note creation** (`app/models/note_crud.py:23-55`):
   - `encrypt("")` returns `"", None, None`, so new notes are persisted with empty ciphertext when users leave content blank or start with a new note stub.
   - Cache is updated at creation time, but the entry disappears after restart because of step (1).

## Root Cause
On startup, `populate_cache_from_db` skipped notes whose `content` column was an empty string. When the server later rendered the note tree, the renderer treated the missing cache entry as fatal corruption. The database contents were intact; the fault was a cache population guard that treated empty strings as “no content.”

## Fix
- Treat empty strings as valid content during cache population and refresh.
- Raise immediately if `content` is `NULL`, because that indicates true data corruption.
- After the change, manually invoked cache population against the existing `notes.db` and confirmed `get_cached_content('f22c2495-c1e6-4c85-9e55-6b8ee9496e96')` returns `""`.

## Recommendations
1. Add regression tests covering cache hydration with empty-string notes (new fixtures or service-level test).
2. Consider a migration that normalizes any `NULL` content fields to empty strings and asserts non-null constraint going forward.
3. Extend health checks to compare cache size against `SELECT COUNT(*) FROM notes` to surface discrepancies proactively.
