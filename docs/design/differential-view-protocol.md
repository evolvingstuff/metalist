# Differential View Protocol

## Overview
- `/api/notes/view` now supports JSON responses when the client sends `Accept: application/json` (or `?format=json`).
- The server reuses the in-memory `NoteStore` to build a preorder structure snapshot plus render variants and hashes for each visible note.
- Clients retain HTML fallback automatically if JSON negotiation fails or is disabled.

## Payload Shape
```json
{
  "structure": [
    {
      "id": "note-id",
      "parentId": null,
      "prevId": null,
      "nextId": "sibling-id",
      "hash": "sha256"
    }
  ],
  "notes": {
    "note-id": {
      "content": "<div>rendered html</div>",
      "rawContent": "<div>plaintext</div>",
      "flags": {
        "isEditing": false,
        "isCollapsed": false
      },
      "variants": {
        "collapsed": "<div>…",
        "expanded": "<div>…",
        "edit": "<div>…"
      },
      "hashes": {
        "collapsed": "sha256",
        "expanded": "sha256",
        "edit": "sha256"
      },
      "metadata": {
        "parentId": null,
        "prevId": null,
        "nextId": "sibling-id",
        "isCollapsed": false,
        "createdAt": "2024-01-01T00:00:00",
        "updatedAt": "2024-01-01T00:00:00"
      }
    }
  },
  "locks": {
    "note-id": "client-id"
  },
  "version": "app-version",
  "updateUUID": "sync-token",
  "treeHash": "sha256",
  "editingNoteId": "note-id",
  "searchQuery": "term",
  "currentClientId": "client-id"
}
```

### Notes
- `structure` is preorder; `prevId`/`nextId` reference visible siblings for deterministic ordering and hash calculation.
- `hash` derives from the expanded variant plus children, so hash changes capture content or structural edits.
- `variants` supply the rendered HTML for collapsed/expanded/edit modes so the client can swap without re-templating.
- `treeHash` is a convenient checksum (id + parent/prev/next/hash) used by the client for coarse equality checks.
- Requests fail fast if the `NoteStore` is not hydrated (server bug) instead of silently degrading.

## Client Reconciliation
- Feature flag `CONFIG.FEATURE_FLAGS.DIFFERENTIAL_VIEW` toggles JSON negotiation.
- `NotesAPI.fetchView` saves the latest `updateUUID` when JSON is returned; HTML fallback remains intact.
- The diff service removes DOM nodes missing from `structure`, moves existing ones to match parent order, and creates new nodes using the payload.
- `ModeContext` tracks per-note hashes and the `treeHash` to short-circuit redundant DOM writes. Editing notes held by the current client skip content replacement unless their hash changes to avoid clobbering unsaved work.
- Lock state, collapse flags, and memory-mode styling are applied directly from `flags` + `locks`.

## Manual Verification Checklist
- Exercise note CRUD (create, edit, delete) and confirm only changed nodes rerender.
- Move notes across parents/siblings and ensure DOM order updates without full redraw.
- Toggle collapse/expand and verify children remain intact; run `updateCollapseAffordances` once per refresh.
- Perform undo/redo flows; the structure should reconcile cleanly, and sync UUIDs advance.
- Run search filtering (including clearing the query) to confirm filtered structures diff correctly and hashes realign.

## Follow-ups
- Extend automated tests once the pytest harness migrates to the sqlite helpers (current suite still pending).
- Consider persisting `variants` client-side for future mode transitions (e.g., inline collapse) without another payload.
