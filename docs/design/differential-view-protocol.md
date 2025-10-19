# Differential View Protocol

## Overview
- `/api/notes/view` accepts JSON `POST` requests in “diff mode”.
- The server always renders the full note tree with the existing renderer, then emits only the delta relative to hashes supplied by the client.
- HTML fallback is removed; clients that do not send the diff payload should continue to use the legacy HTML endpoint (handled separately).

## Request Shape
```json
{
  "clientId": "client-uuid",
  "editingNoteId": null,
  "search": "optional query",
  "clientNoteUuidHashes": [
    ["note-uuid-1", "sha256hash1"],
    ["note-uuid-2", "sha256hash2"]
  ]
}
```

### Notes
- `clientNoteUuidHashes` is a list of `[noteId, expandedHashWithFlags]` tuples representing the client’s current cache. Omit entries the client does not have (they will be treated as additions).
- `clientId`, `editingNoteId`, and `search` retain their current semantics.
- The client issues the diff request whenever it needs to reconcile with the server: after detecting a changed `updateUUID` from `/api/notes/check-updates`, or immediately after local mutations (save, move, collapse toggles, exiting edit mode) to pick up server-side side effects.

## Response Shape
```json
{
  "html": "<div>existing SSR output…</div>",
  "structure": [
    ["note-uuid-1", null, null, "note-uuid-2"],
    ["note-uuid-2", null, "note-uuid-1", null]
  ],
  "updatedNotes": [
    [
      "note-uuid-2",
      {
        "content": "<div>rendered html</div>",
        "flags": {
          "isEditing": false,
          "isCollapsed": false,
          "memoryMode": false
        },
        "hash": "sha256hash2"
      }
    ]
  ],
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
- `html` is temporarily included for compatibility with the legacy DOM refresh path while the client migrates to the pure diff workflow.
- `structure` is preorder, each entry is `[id, parentId|null, prevId|null, nextId|null]`. Include every visible node so the client can reorder DOM as needed.
- `updatedNotes` lists only the nodes whose expanded hash differs from what the client reported (or nodes the client lacks). Each entry is `[id, payload]` where `payload` includes the rendered expanded HTML, flags, and the server’s latest expanded hash. The hash incorporates both the expanded HTML and the note’s flag state (e.g., `isCollapsed`, `isEditing`, `memoryMode`).
- Any note id missing from `structure` should be removed client-side; no explicit removal list is returned.
- Locks, version, search info, and `updateUUID` mirror the existing HTML response so downstream code keeps working.

## Client Reconciliation
- Maintain a cache of `[id, hash]` tuples in `ModeContext`; convert the response `updatedNotes` list into map form when updating the DOM.
- Walk `structure` to ensure DOM order matches the server. Insert new nodes when they appear, reposition existing nodes based on `prevId/nextId`, and establish child containers as today.
- For each entry in `updatedNotes`, update content/flags and refresh the stored hash.
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
