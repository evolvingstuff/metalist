# Differential View Protocol

## Overview
- `/api2/notes/view` accepts JSON `POST` requests in “diff mode”.
- The server builds a snapshot from the in-memory `NoteStore` and emits only the delta relative to hashes supplied by the client.
- HTML fallback is removed; clients that do not send the diff payload should continue to use the legacy HTML endpoint (handled separately).

## Request Shape
```json
{
  "clientId": "client-uuid",
  "editingNoteId": null,
  "search": "optional query",
  "clientSeenRootIds": ["root-uuid-1", "root-uuid-2"],
  "clientNoteUuidHashes": {
    "note-uuid-1": "sha256hash1",
    "note-uuid-2": "sha256hash2"
  }
}
```

### Notes
- `clientSeenRootIds` identifies which root notes have actually been visible in the viewport; the server uses this to decide when to append additional root batches.
- `clientNoteUuidHashes` is a map of `noteId -> expandedHashWithFlags` representing the client’s current cache. Omit entries the client does not have (they will be treated as additions).
- `clientId`, `editingNoteId`, and `search` retain their current semantics.
- The client issues the diff request whenever it needs to reconcile with the server: after detecting a changed `updateUUID` from `/api2/notes/check-updates`, or immediately after local mutations (save, move, collapse toggles, exiting edit mode) to pick up server-side side effects.

## Response Shape
```json
{
  "structure": [
    {
      "id": "note-uuid-1",
      "parentId": null,
      "prevId": null,
      "nextId": "note-uuid-2",
      "hash": "sha256hash1"
    },
    {
      "id": "note-uuid-2",
      "parentId": null,
      "prevId": "note-uuid-1",
      "nextId": null,
      "hash": "sha256hash2"
    }
  ],
  "notes": {
    "note-uuid-2": {
      "content": "<div>rendered html</div>",
      "flags": {
        "isEditing": false,
        "isCollapsed": false,
        "memoryMode": false,
        "memorySelected": false
      },
      "hash": "sha256hash2"
    }
  },
  "locks": {
    "note-uuid-1": "client-uuid"
  },
  "updateUUID": "sync-token",
  "version": "app-version",
  "currentClientId": "client-uuid",
  "searchQuery": "optional query",
  "editingNoteId": null
}
```

### Notes
- `structure` is preorder; each entry includes `id`, `parentId`, `prevId`, `nextId`, and the authoritative `hash`. Include every visible node so the client can reorder DOM as needed. When infinite scrolling is enabled, the server appends new root nodes as the window expands but keeps previously delivered roots present so clients never drop hashes.
- `notes` maps only the nodes whose expanded hash differs from what the client reported (or nodes the client lacks). Each value contains normalized flags and the latest hash. The hash incorporates content, normalized flags (e.g., `isCollapsed`, `isEditing`, `memoryMode`, `memorySelected`), and the parent/prev/next pointers so structural changes trigger updates.
- Any note id missing from `structure` should be removed client-side; no explicit removal list is returned.
- Locks, version, search info, and `updateUUID` mirror the existing HTML response so downstream code keeps working.

## Client Reconciliation
- Maintain a map of `id -> hash` in `ModeContext`; populate it from `structure` hashes each response and drop entries for ids no longer present.
- Walk `structure` to ensure DOM order matches the server. Insert new nodes when they appear, reposition existing nodes based on `prevId/nextId`, and establish child containers as today.
- For each entry in `notes`, update content/flags and refresh the stored hash. Nodes absent from `notes` retain their existing content/flags but may still move according to the structure.
- Remove DOM nodes that are not present in the latest `structure`; also drop their hashes from local cache.
- Persist `updateUUID` for continued sync polling.

## Manual Verification Checklist
- CRUD sequences: create, edit, delete and confirm only changed nodes rerender.
- Structural mutations: move notes across parents/siblings and verify DOM order updates without full redraw.
- Collapse/expand toggles: ensure child containers and flags stay accurate.
- Undo/redo flows: structure diff should realign with no stale nodes.
- Search filtering: filtered structures should diff correctly; stale hashes should trigger payload updates.
- Lock acquisition/release: verify lock icons/styling update without full refresh.

## Follow-ups
- Investigate compression/streaming for large `clientNoteUuidHashes` payloads if needed.
- Extend automated tests once the pytest harness migrates to the sqlite helpers (current suite still pending).
- Explore caching rendered variants server-side if diff CPU becomes material after the protocol change.
