# Differential View Update Plan

## Objectives
1. Avoid re-sending full HTML for `/api/notes/view`; deliver structural diffs + note payloads.
2. Reuse existing `NoteStore` hashes to help the client detect changes.
3. Update the client refresh path to reconcile the structure/content payload with minimal DOM work.
4. Document the protocol and testing implications.

## Server Tasks
1. **Structure Snapshot API**
   - Expose a preorder list from `NoteStore` for visible notes (id, parent_id, prev_id, hash).
   - Provide a helper that produces `{ structure: [...], notes: {id: {content, variants}} }` given the render context.

2. **/api/notes/view Response**
   - Modify the endpoint/service to return the JSON payload instead of HTML when the client requests differential mode (e.g., `Accept: application/json` or new query param).
   - Ensure existing HTML response remains available (fallback compatibility).

3. **Sync UUID Integration**
   - Include the `updateUUID` in the new payload so polling can reuse it.

## Client Tasks
1. **Transport Negotiation**
   - Update `NotesAPI.fetchView` to request JSON when differential updates are enabled.
   - Maintain fallback to HTML for legacy paths.

2. **Diff Application**
   - Cache the last structure + note hashes on the client.
   - Compare incoming structure to existing state to detect additions/removals/reorders.
   - For changed/new notes, apply the provided content HTML (expanded/collapsed/edit variants) to the DOM.
   - Remove any notes not present in the new structure.

3. **State Persistence**
   - Update `ModeContext` to store the latest note hashes for reference.
   - Ensure collapse state, locks, and search context stay in sync with the hash-based updates.

## Testing & Documentation
1. Update or add docs describing the differential update protocol (`docs/design` or new doc).
2. Manual verification: CRUD + move + collapse + undo/redo + search filtering to ensure UI updates without full-page re-render.
3. Note pytest harness remains pending rewrite; ensure the new server helpers are covered once the test suite migrates.

## Risks / Watchouts
- Client state must stay consistent if an update is missed (e.g., network hiccup); may need a recovery path to request full render.
- Need to ensure hashes include all metadata that affects the UI (collapsed state, locks, encryption status).
- Keep performance in mind: hashing and payload construction should remain fast for large note hierarchies.
