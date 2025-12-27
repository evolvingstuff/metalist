# PLAN: Server-Side Cached Views + Incremental Ops

## Goal
Stop shipping multi-megabyte `snapshot.structure` payloads for `/api2/notes/view` by having the server cache each tab's last rendered view and return only the minimal DOM ops (insert/move/remove/update) plus changed note payloads. Full snapshots become limited to initial loads (first chunk) or cache misses, so steady-state latency and payload size drop sharply.

## Context
- Client already maintains per-tab DOM state and hashes.
- `applyDifferentialView` currently diffs against a full structure list from the server.
- Server rebuilds the entire requested prefix on every call, yielding ~3 MB responses and ~300 ms CPU time.

## Phases

### 1. Define Operation Protocol
- Operation types: `insert`, `remove`, `move`, `update`, `replaceParent` (if necessary), `syncMetadata` (locks, flags).
- Each op includes minimal data (ids, parent, indices, payload when needed).
- Decide serialization format (probably list of JSON objects) and include a version number for future-proofing.

- Add a module (e.g., `app/services/view_cache.py`) storing `tab_id -> CachedView` where `CachedView` holds:
  - Ordered child lists per parent (root + nested) as last sent.
  - Hashes/flags per note id to detect content changes.
  - Metadata (editing note, locks, scroll offset) relevant to that view.
- Cache key: `(client_id, tab_id, search_query)` to keep search tabs distinct.
- Keep the cache purely in-memory (no disk persistence). As long as the server stays up we can restore tab/scroll state when the browser reconnects; after a server restart we fall back to the initial snapshot flow.
- Provide helpers: `get_cached_view(key)`, `update_cached_view(key, new_view)`, `invalidate(key)`.

### 3. Snapshot Builder Refactor
- Split `build_view_snapshot` into:
  1. `build_view_state(...)` – compute the desired view (structure + payloads) for the requested window (still windowed to first chunk or viewport slice). This is similar to existing logic but returns an in-memory `ViewState`, not serialized lists.
  2. `diff_view_states(prev, current)` – produce op list by comparing cached `prev` (if any) to `current`.
- When cache miss (no `prev`): send `fullSnapshot` payload (first chunk) that matches current client expectations; cache it afterward.
- When cache hit: send `diffOps` payload and update cache with `current`.

### 4. Client Changes
- Update `NotesAPI.fetchView` to send `tabId` / search context so the server can select the proper cached view.
- Extend `applyDifferentialView` (or add a new executor) to consume op lists when `snapshot.diffOps` exists, falling back to the current full-structure diff when `snapshot.structure` is present (backwards compatibility).
- Adjust ModeContext to handle `fullSnapshot` vs. `diffOps` responses (e.g., replace DOM vs. apply ops) without reimporting entire structure each time.
- Ensure tab switches reuse local DOM; they only call `/notes/view` in cases where new data is needed (e.g., user edits elsewhere).

### 5. Window/Chunk Handling
- `build_view_state` still respects root windowing (initial chunk + expansions) so "full" snapshots never exceed the configured limit (e.g., 50-100 roots).
- Future optimization: track approximate screen height/DOM size (not just root count) so massive single-root trees (e.g., one note with 50k children) can be windowed intelligently, progressively loading more children as the user scrolls deeper into that note.
- When the client scrolls and requests more, the server expands the cached view and emits insert ops for the new roots/children; no need to resend earlier ones.

### 6. Edge Cases & Recovery
- Cache invalidation triggers: server restart (no cache), undo/redo across tabs, search query modifications, auth logout.
- Provide a `forceFullSnapshot` flag the server can send if it detects divergence (e.g., parent mismatch) so the client replaces its DOM and cache is reset.
- Handle editing note pinning: if current edit target leaves the cached window, ensure `build_view_state` includes it and emits update ops as needed.

### 7. Instrumentation / Verification
- Add debug logging for op counts, payload sizes, and diff timings.
- Compare before/after: same user action should drop from 3 MB/300 ms to tens of KB/<100 ms.
- Add unit tests for `diff_view_states` and cache lifecycle; add integration test covering cache miss → diff → cache hit.

### 8. Documentation & Rollout
- Update `docs/design/differential-view-protocol.md` with the new op-based contract and cache semantics.
- Keep a feature flag to fall back to old behavior if unforeseen issues arise.
