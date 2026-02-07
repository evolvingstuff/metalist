# PLAN: Mouse Drag Note Movement (Directional)

## Goals
- Add mouse drag gesture to move a note (and subtree) exactly one step in a cardinal direction.
- Drag gestures only apply when **not** editing and only when `mousedown` starts on the note body.
- A drag is recognized only if the pointer moves beyond a distance threshold; otherwise it is a normal click.
- When a drag is active, show a “grabbing” cursor; if the pointer returns within the threshold, revert and treat as a click.
- Movement uses the same backend logic as keyboard moves (indent/outdent/up/down).
- Indent should only happen if there is a **visible** sibling above; it should indent under that visible sibling.

## Non-Goals
- Free-form drag/drop placement or reparenting by cursor position.
- Drag gestures while editing.
- Multi-step moves per drag (exactly one move per gesture).
- Cypress tests in this iteration.
- Reworking undo/redo beyond existing move behavior.

## Behavioral Notes (from PLAN.note-movement.md)
- Indent: selected note becomes the last child of the **visible** sibling immediately above it.
- Outdent: selected note becomes a sibling after its parent.
- Move Up/Down: swap with the **visible** adjacent sibling. Hidden siblings keep their relative order.
  - Example: `A (B) (C) D E`, move E up → `A (B) (C) E D`.
  - Example: `A (B) C (D) E`, move E up → `A (B) E C (D)`.
- No-ops are silent (no error, no move).
- Only the selected note + subtree move.

## Open Questions / Assumptions
- For **Move Up/Down** in filtered views: assume “adjacent visible sibling” (like indent) rather than hidden siblings.

## Plan
1. **Gesture state**: add a drag tracker for `mousedown`/`mousemove`/`mouseup` on the note body.
   - Ignore if editing or if `mousedown` is not on a note body.
   - Store start coords and note id.
2. **Threshold + cursor**:
   - Compute distance from start on `mousemove`.
   - If distance >= threshold, mark drag-active and set cursor to grabbing.
   - If distance drops back below threshold, revert to click state and cursor.
3. **Direction resolution**:
   - On `mouseup`, if drag-active, compute angle or compare `abs(dx)` vs `abs(dy)` to pick cardinal direction.
   - Prevent the click-from-triggering-edit in this path.
4. **Execute move**:
   - Use existing move actions:
     - Up/Down: move by visible sibling (assumption above).
     - Right/Left: indent/outdent (indent uses visible sibling above).
   - Wrap in `CommandGate.run(...)` like keyboard actions.
5. **Styling**:
   - Add a CSS class on `body` or `#notes-container` for drag state to control cursor (`grab`/`grabbing`).
6. **Manual test pass** (no Cypress):
   - Drag within threshold → normal click/edit.
   - Drag past threshold → move exactly one step; no click edit.
   - Drag past threshold then back inside → normal click/edit.
   - Move up/down/indent/outdent with visible sibling rules.

## Manual Test Checklist
- `mousedown` on note body, tiny move, `mouseup`: behaves like click (enters edit).
- Drag past threshold: cursor changes to grabbing, no click/edit fires.
- Drag back near start then `mouseup`: acts like click (enters edit).
- Indent only with visible sibling above.
- Move up/down respects visible siblings in filtered views.

## Files (Expected Touch Points)
- `app/static/js/modules/mode-manager/events/keyboard-events.js` (or a new mouse/drag handler module)
- `app/static/js/modules/mode-manager/actions/note-actions.js`
- `app/static/js/modules/mode-manager/services/*` (if adding drag state helpers)
- `app/static/css/*` (cursor classes)
