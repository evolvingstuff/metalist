# PLAN: Drag & Drop Notes

## Goals
- Add mouse-based drag and drop for notes (including their children) with clear visual affordances.
- Support dropping as a sibling (before/after another note) or as a child of another note.
- Keep the UI stable during drag (no DOM reordering or view refresh until drop).
- Only allow drag/drop when **not** in note edit/selection mode.

## Non-Goals
- No touch/mobile drag support in this pass.
- No multi-select or multi-note dragging.
- No changes to keyboard move shortcuts.

## Constraints / Current Architecture
- Notes are rendered as nested `.note` elements with `.note-children` containers in `app/templates/notes_list.html`.
- Move API: `POST /api2/notes/{note_id}/move` expects `sibling_id`, `position`, `new_parent_id` (required in request body) and uses `CmdMove`.
- `CmdMove` currently **fails fast** if `sibling_id` or `position` are missing. This blocks a “move into empty child list” scenario.
- UI updates are driven by `actionRefreshAndMaybeSelect()` + differential view; avoid calling this during drag.
- `CommandGate.run()` is the only allowed boundary to trigger server-bound actions.
- Drag/drop state must live inside ModeManager (ModeContext + mode-manager services). No separate global state machine.
- Project rule: no default params or defaulting operators; prefer explicit values and explicit branches.

## UX / Interaction Spec
- Drag handle appears on hover for non-editing notes. Clicking the handle does **not** select or edit.
- Cursor states:
  - `grab` on handle (idle).
  - `grabbing` while drag is active.
  - `not-allowed` when hovering an invalid drop target.
- While dragging:
  - The original note (and its subtree) remains in place and is visually muted (opacity/blur).
  - A lightweight drag “ghost” follows the cursor (optional but recommended for feedback).
  - Drop indicators show where the note will land:
    - Top band → sibling **before** target.
    - Bottom band → sibling **after** target.
    - Middle band → **child** of target.
- Drop indicators must not shift layout (use pseudo-elements/outline/box-shadow).

## Drag State (ModeManager-Integrated)
- States tracked via ModeContext fields (e.g., `isDragging`, `dragNoteId`, `dragTargetId`, `dragPosition`).
- Lifecycle:
  - Idle
  - Armed (mouse down on handle, threshold not yet met)
  - Dragging
  - Dropped (valid target)
  - Cancelled (invalid target / escape / mouseup with no target)
- No standalone state-machine module; logic is coordinated by ModeManager services and ModeContext state.

## Target Resolution Rules
- Determine the hovered `.note` element under pointer (excluding the dragged note and its descendants).
- Compute drop zone based on pointer Y within the target note’s bounding box:
  - Top 25%: BEFORE
  - Bottom 25%: AFTER
  - Middle 50%: INSIDE (child)
- Invalid targets:
  - The dragged note itself.
  - Any descendant of the dragged note (would create a cycle).
  - Locked notes (no interaction).
- Root-level drop:
  - If pointer is above first root note → insert BEFORE first root.
  - If pointer is below last root note → insert AFTER last root.

## Move Payload Strategy
- Sibling drop:
  - `sibling_id = targetNoteId`
  - `position = BEFORE | AFTER`
  - `new_parent_id = null` (explicit)
- Child drop (target has children):
  - `new_parent_id = targetNoteId`
  - Insert at the **front** of the child list.
  - `sibling_id = firstChildId`
  - `position = BEFORE`
- Child drop (target has **no** children):
  - Requires backend change to allow `sibling_id = null` and `position = null`
  - Semantics: insert as **first** child under `new_parent_id`.

## Backend Adjustments
- `app/api/routes/notes.py`:
  - Accept explicit `null` for `sibling_id` and `position` (still required keys).
- `app/usecases/move.py` (`CmdMove.execute`):
  - Allow `sibling_id is None` iff `new_parent_id` is provided and `position is None`.
  - Treat this as “insert at head of new_parent_id child list”.
  - Preserve fail-fast behavior for other invalid combinations.

## Frontend Changes
- `app/templates/notes_list.html`:
  - Add drag handle element inside `.note` (e.g., `<button class="drag-handle" ...>` or `<span ...>`).
  - Ensure it’s not focusable when editing (or hidden via CSS).
- `app/static/css/main.css`:
  - Style drag handle visibility on hover.
  - Add `body.dragging` cursor.
  - Refine `.note.drag-before`, `.note.drag-after`, `.note.drag-inside`, `.note.dragging` to avoid layout shift.
  - Add ghost element styles if used.
- ModeManager service: `app/static/js/modules/mode-manager/services/drag-drop-service.js`:
  - Coordinates drag behavior and DOM updates.
  - All state lives in ModeContext (no separate state machine).
  - Expose `isDragging()` for other modules to gate behavior.
- `app/static/js/modules/mode-manager/events/mouse-events.js`:
  - Initialize drag service.
  - Ignore click/selection actions if a drag is in progress or was just completed.
- `app/static/js/modules/mode-manager/actions/note-actions.js`:
  - Add `moveNoteByDrag()` action: validates state, calls API via `CommandGate.run`, then refreshes view.
- `app/static/js/modules/api-client.js`:
  - Ensure `moveNote()` always includes `new_parent_id` (explicit `null` allowed).
  - Add validation to reject `undefined` inputs rather than defaulting.
- `app/static/js/modules/mode-manager/services/infinite-scroll-service.js`:
  - Skip polling when drag is active to prevent mid-drag view refresh/jump.

## Documentation
- Defer doc updates until behavior is stable.
- Update `docs/ui/controls.md` with DnD behavior and constraints.
- Consider new doc: `docs/ui/drag-drop.md` if behavior grows (optional, but recommended).

## Implementation Steps
1. Add drag handle markup to `app/templates/notes_list.html`.
2. Add ModeContext fields for drag state (no separate state machine).
3. Implement drag/drop service module (hit-testing, indicators, cleanup).
4. Wire service initialization into mode manager startup and mouse event gating.
5. Add drag CSS (cursor, muted source note, drop indicators, ghost styling).
6. Implement `moveNoteByDrag()` action with `CommandGate.run` + `NotesAPI.moveNote()`.
7. Backend: relax `CmdMove` validation for `sibling_id = null` + `position = null` when `new_parent_id` is provided.
8. Tighten API client validation to require explicit `new_parent_id` in move calls.
9. After code is stable, update docs.

## Testing / Validation
- Manual tests:
  - Drag root note before/after another root.
  - Drag note into another note with children (append/prepend behavior confirmed).
  - Drag note into another note with **no** children (requires new backend behavior).
  - Attempt drop onto own descendant → should show invalid cursor, no move.
  - Drag while editing a note → handle hidden/disabled; no drag.
  - Ensure no DOM reflow/jump while dragging.
- If time permits, add Cypress E2E for a basic drag/drop reorder.

## Open Decisions to Confirm
- Child drop placement: append to end vs insert at top (plan assumes append).
- Whether to show a drag ghost or rely on cursor + indicators only.
