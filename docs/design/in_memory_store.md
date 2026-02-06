# In-Memory Note Store Design

## Goals
- Load the entire note hierarchy into memory at startup.
- Avoid runtime SQL reads during normal operation (enforced by a post-startup read guard).
- Provide fast lookups for rendering, search, and hierarchy manipulation.
- Keep undo/redo viable (temporary DB reads are permitted via explicit guard overrides).

## Core Components (As Implemented)
- `app/services/note_store.py` (`store`): canonical in-memory graph holding decrypted note content + tags + ordering metadata.
- `app/services/content_cache.py`: decrypts note content + tags from DB into in-memory caches.
- `app/services/search_index.py`: in-memory search index (tag postings + trigram postings) maintained from `NoteStore` mutations.
- `app/services/snapshot.py`: builds the view snapshot used by `POST /api2/notes/view`.
- `app/db/session.py`: provides `begin_writer()`/`connect_reader()` and enforces the post-startup SELECT guard.

## Data Model (Conceptual)
Notes are treated as a linked structure:
- `parent_id`: tree hierarchy
- `prev_id` / `next_id`: sibling ordering within a parent

The in-memory store maintains enough indices to:
- answer “get children in order” quickly
- update local link invariants on move/insert/delete

## Startup Flow
At a high level (`app/main.py`):
1. Initialize DB schema + ensure settings exist.
2. If encryption is **disabled**:
   - Prefetch all note rows.
   - Populate the decrypted content cache.
   - Hydrate the in-memory note store from the prefetched rows.
   - Enable the read guard so accidental runtime `SELECT` crashes loudly.
3. If encryption is **enabled**:
   - Skip cache + note-store hydration at startup.
   - Enable the read guard immediately.
   - Hydration happens after login via `/api2/auth/hydrate`, and the UI shows a first-load progress indicator.
   - Progress is reported across hydration phases (decrypt, note store, tag inference, search index, matcher inference) to keep the bar monotonic.

## View / Diff Flow
- Route: `POST /api2/notes/view` (`app/api/routes/notes.py`)
- Snapshot builder: `app/services/snapshot.build_view_snapshot(...)`
- Diffing behavior:
  - The server always returns authoritative `snapshot.structure`.
  - `snapshot.notes` is filtered to only include notes whose `hash` differs from the client’s `clientNoteUuidHashes`.

See `docs/design/differential-view-protocol.md` for the wire format.

## Read Guard
The project enforces a “no runtime SELECTs after startup” rule:
- `app/db/session.py` wraps sqlite connections in `GuardedConnection` and raises `RuntimeError("Post-startup DB read forbidden")` when a `SELECT` is attempted after the guard is enabled.
- Writers (`begin_writer`) are used for write transactions.
- Explicit read windows exist via `connect_reader(reason=...)` or `allow_reads(reason=...)`.

## Undo/Redo Guard Exception
Undo/redo workflows can legitimately need DB reads (e.g., replay validation or hydration). Those should happen only inside explicit allow-read windows.

## Testing Notes
Backend unit/integration tests are currently not the primary coverage (see `docs/testing/harness.md`). If rebuilding backend coverage, the highest-value tests are:
- NoteStore invariants: load, insert, delete, move, collapse/expand
- Guard behavior: runtime `SELECT` crashes after startup; allow-read contexts work as expected
