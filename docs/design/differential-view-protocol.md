# Differential View Protocol

## Overview
- `POST /api2/notes/view` accepts JSON requests in “diff mode”.
- The server builds a view `snapshot` from the in-memory store and returns:
  - `snapshot.structure`: the authoritative visible tree/order
  - `snapshot.notes`: only the notes whose `hash` differs from what the client reported
- This is the current view endpoint; legacy `/api/*` routes are hard-blocked.

## Request Shape
```json
{
  "clientId": "client-uuid",
  "editingNoteId": null,
  "search": "optional query",
  "clientSeenRootIds": ["root-uuid-1", "root-uuid-2"],
  "clientNoteUuidHashes": {
    "note-uuid-1": "expandedHashWithFlags",
    "note-uuid-2": "expandedHashWithFlags"
  }
}
```

### Notes
- All top-level keys above are treated as required by the current handler.
- `clientSeenRootIds`: roots that have actually been visible in the viewport; used to decide when to append additional root batches (infinite-scroll/windowing).
- `clientNoteUuidHashes`: map of `noteId -> hash` representing the client cache. Omit entries the client does not have.
- `search` and `editingNoteId` are passed through for server-side rendering/flagging.

## Response Shape
```json
{
  "snapshot": {
    "structure": [
      {
        "id": "note-uuid-1",
        "parentId": null,
        "prevId": null,
        "nextId": "note-uuid-2",
        "hash": "expandedHashWithFlags"
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
        "hash": "expandedHashWithFlags"
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
  },
  "updateUUID": "sync-token"
}
```

### Notes
- `snapshot.structure` includes every visible node so the client can reorder/insert/remove DOM nodes as needed.
- `snapshot.notes` is a sparse map: only nodes whose `hash` differs from the client’s reported `clientNoteUuidHashes`.
- Any note id missing from `snapshot.structure` should be removed client-side; no explicit removal list is returned.
- `updateUUID` is duplicated at the top level for convenience; it matches `snapshot.updateUUID`.

## Client Reconciliation
- Maintain a map of `id -> hash` from the latest `snapshot.structure`.
- Walk `snapshot.structure` to ensure DOM order matches the server. Insert nodes that appear; reposition existing nodes based on `prevId/nextId`.
- Apply payloads from `snapshot.notes` to update content/flags and refresh stored hashes.
- Remove DOM nodes that are absent from the latest `snapshot.structure` and drop their hashes.

## Manual Verification Checklist
- CRUD sequences: create, edit, delete and confirm only changed nodes rerender.
- Structural mutations: move across parents/siblings and verify order updates without full redraw.
- Collapse/expand toggles: child containers + flags stay accurate.
- Undo/redo flows: structure diff realigns with no stale nodes.
- Search filtering: filtered structures diff correctly.
- Lock acquisition/release: lock icons/styling update without full refresh.
