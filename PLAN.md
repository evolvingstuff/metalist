# PLAN: Keyboard Indent/Outdent

## Goals
- Add `Cmd+Left` / `Cmd+Right` to outdent/indent the selected note (and subtree) while editing.
- Introduce explicit endpoints: `POST /api2/notes/{id}/indent` and `POST /api2/notes/{id}/outdent`.
- When outdenting to root in a non-empty search context, ensure the note’s tag bar includes required positive tag terms and `/*text*/` comments, without removing any existing tags.
- Ensure undo/redo restores tags when outdent-to-root added tags.

## Non-Goals
- Mouse/drag gesture movement.
- Cypress tests in this iteration.
- Reworking the entire undo/redo model.

## Behavioral Notes (from PLAN.note-movement.md)
- Indent: selected note becomes the last child of the sibling immediately above it.
- Outdent: selected note becomes a sibling after its parent.
- No-ops are silent (no error, no move).
- Only the selected note + subtree move.

## Plan
1. Backend: extract shared “ensure tags match search query” helper from `app/usecases/paste_sibling.py` to a reusable module.
2. Backend: implement `CmdIndent` and `CmdOutdent` (or equivalent usecases) that compute new parent/prev/next via `store.children(...)` ordering, then call `apply_move`.
3. Backend: when outdenting to root and `search_query` has required terms, update tags using the shared helper before returning.
4. Backend: extend move undo recording to include `before_tags` and `after_tags`, and update undo/redo to restore tags when applying the inverse move.
5. API: add `POST /notes/{note_id}/indent` and `POST /notes/{note_id}/outdent` routes.
6. Frontend: add config endpoints, API client methods, and note actions for indent/outdent.
7. Frontend: wire `Cmd+Left` and `Cmd+Right` in `keyboard-events.js` (active while editing).
8. Manual test pass (no Cypress): verify indent/outdent, no-op edges, and tag/undo behavior in search contexts.

## Manual Test Checklist
- Indent while editing: selected note with a previous sibling becomes its last child.
- Indent no-op: first sibling does nothing.
- Outdent while editing: selected note becomes sibling after parent.
- Outdent no-op: root note does nothing.
- Search context `foo "bar"`: outdent-to-root adds `foo` and `/*bar*/` to tag bar without removing existing tags.
- Undo restores prior tags; redo re-applies tag additions.

## Files (Expected Touch Points)
- `app/usecases/paste_sibling.py` (helper extraction)
- `app/usecases/indent.py` and `app/usecases/outdent.py` (new)
- `app/usecases/move.py` (move undo capture)
- `app/services/undo_state.py` (move undo/redo tags)
- `app/api/routes/notes.py` (new endpoints)
- `app/static/js/modules/config.js`
- `app/static/js/modules/api-client.js`
- `app/static/js/modules/mode-manager/actions/note-actions.js`
- `app/static/js/modules/mode-manager/events/keyboard-events.js`

