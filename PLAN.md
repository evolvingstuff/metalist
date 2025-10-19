# Infinite Scroll Plan

## Goals
- Lazily load root notes so the client initially renders only the first 50 visible roots and fetches more when the user scrolls near the bottom.
- Preserve existing diff-based reconciliation (structure + payload hashes) while avoiding duplicate work for already loaded notes.
- Ensure collapsed branches remain hidden and editable notes still include their descendants even when outside the current viewport.

## Assumptions
- The client can report the lowest root note currently visible on screen; collapsed notes cannot be visible.
- Requests already include all hashes the client knows about via `clientNoteUuidHashes`, so the server does not need to track prior window state.
- Infinite scroll focuses exclusively on root notes; descendants continue to be delivered with their parent root as today (subject to collapse/edit rules).

## High-Level Approach
1. **Request Contract** – Extend `/api/notes/view` to accept `clientSeenRootIds` so the server knows which delivered roots have actually entered the viewport.
2. **Server Windowing** – Modify `NoteQueryService.build_view_snapshot` to page root notes:
   - Determine the ordered list of root ids.
   - Compute the window to include: start at the top, include 50 roots initially; when the newest root the client has actually seen falls within 25 of the current tail, append the next chunk of 50.
   - Retrieve all descendants for the selected root subset (respecting collapsed/editing logic).
3. **Client Scroll Logic** – Maintain two root-note sets (`knownRoots`, `seenRoots`) so the client understands which delivered roots have actually entered the viewport. A lightweight polling loop (e.g., every 500 ms) inspects visible root ids, moves any newly visible ones from `knownRoots` to `seenRoots`, and when the count of unseen-but-known roots drops below the buffer threshold, we refresh `/view`.
4. **Hash / Diff Handling** – The server will continue returning all previously delivered roots in `structure`, simply appending new ones as the window expands, so existing hashes remain valid.
5. **Testing & Instrumentation** – Add targeted unit coverage around the server windowing logic and exercise client behaviour manually (scrolling, editing, collapse toggles) to confirm seamless loading.

## Detailed Tasks

### 1. API & Server Updates
- Update `ViewDiffRequest` to accept `client_seen_root_ids` (list/set) alongside existing hashes.
- In `NoteQueryService.build_view_snapshot`:
- In `NoteQueryService.build_view_snapshot`:
  - Fetch ordered root ids (likely via `note_store.get_children(parent_id=None)`).
  - Introduce helper to slice root list according to window rules (`CHUNK_SIZE = 50`, `BUFFER = 25`).
  - Use `client_seen_root_ids` to decide when the buffer threshold has been reached; fall back to editing note or prior known roots to guarantee continuity.
  - Always include roots up to the determined window end; never trim earlier ones so existing DOM nodes stay valid.
  - For each included root, emit descendants with existing recursion logic (respecting collapsed/editing flags).
- Ensure payloads include hashes/content for any newly emitted notes.

### 2. Client Adjustments
- Maintain two sets in ModeContext (or a dedicated scroll state module):
  - `knownRootIds`: roots delivered in the latest snapshot.
  - `seenRootIds`: subset of those roots that have actually appeared in the viewport.
- Add a lightweight poller (≈500 ms) that:
  - Collects the root ids currently visible in the DOM.
  - Adds newly visible ids to `seenRootIds` (set semantics prevent duplicates).
  - Removes the same ids from `knownRootIds`’ “unseen” subset.
  - If the number of unseen-but-known roots falls below the buffer threshold (25), fire a `/view` refresh (carrying the usual hash payload plus the updated `clientSeenRootIds`).
- Reset or adjust these sets when structural mutations occur (collapse/expand/delete) so the polling loop reassesses visibility without spamming requests.
- Whenever the active search context (or tab) actually changes its search query (not just focusing the field), clear `seenRootIds` and rebuild `knownRootIds` from the fresh snapshot to avoid stale visibility assumptions.

### 3. Hash Management
- Confirm ModeContext’s hash map can safely retain entries for roots that remain in the DOM; only new roots should append hashes. Avoid removing hashes when the server omits roots (since it no longer will once emitted).
- Verify differential updates still function when the server sends additional roots without re-sending earlier ones.

### 4. Testing & Verification
- Add unit tests for the new windowing helper to cover scenarios:
  - Initial load (no lowest visible root id)
  - Scroll within buffer triggers expansion
  - Repeated requests without new scroll keep window stable
  - Editing within a collapsed root still includes descendants
- Manual QA checklist:
  - Scroll to bottom repeatedly and confirm new roots append smoothly.
  - Collapse/expand roots near window boundaries.
  - Edit a deep note and ensure children load.
  - Undo/redo or remote updates don’t duplicate or skip roots.

### 5. Cleanup & Documentation
- Update developer docs (possibly `docs/state-handling.md`) with new scroll state handling.
- Consider adding logging/metrics on server for window calculations to aid future tuning.
