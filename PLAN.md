# PLAN

## Goal
Fix the undo bug:

- Select note
- Cmd-Del to delete
- Cmd-Z to undo (note reappears)
- Cmd-Z to undo (note should be deselected, but remains selected)

…while enforcing the intended invariant:

- The client must never allow a second user command to execute while a prior server-bound command is in-flight.
- Extra inputs during in-flight are ignored/dropped (NO queuing/coalescing).


## Non-Goals
- Do not introduce queued/coalesced command behavior.
- Do not change existing Cypress specs.


## Phase 1 — Repro + Observability (Confirm Actual Failure Mode)
1. Add a new Cypress spec that reproduces the bug without relying on “pressing fast”.
   - Drive Cmd-Z twice with an explicit “wait for not-loading” signal between them.
   - Assert that the note is not in editing state after the second undo.
2. Add temporary, fail-fast client-side instrumentation to record:
   - Every user command start/end (undo, delete, edit-mode transitions).
   - Every time we drop an input due to “in-flight”.
   - Whether we actually sent 0/1/2 `/api2/notes/undo` requests.
   - Remove this instrumentation once the bug is fixed and test is stable.

Success criteria:
- We can reproduce the bug reliably.
- We know whether the problem is:
  - (A) second Cmd-Z is not sent (input dropped), OR
  - (B) second Cmd-Z is sent but undo history semantics keep the note selected.


## Phase 2 — Enforce a Single Command Gate (Drop Inputs While In Flight)
3. Implement a single client-side command gate (mutex) with a tiny API, e.g.:
   - `CommandGate.run(name, asyncFn)`
   - `CommandGate.isBusy()`
   - It must set/unset the busy flag in a `finally`.
4. Route ALL user-initiated server-bound actions through the gate:
   - Delete, undo/redo, create, move, edit-mode transitions, save.
   - Ensure click handlers don’t “fire and forget” async actions without going through the gate.
5. Update keyboard/mouse handlers to:
   - If gate busy: drop the input, log a single structured “dropped input” event, and return.
   - Never queue.

Success criteria:
- It is impossible to send two user commands concurrently.
- DevTools Network shows at most one in-flight command request at any time.


## Phase 3 — Fix Undo Semantics (Deselect on 2nd Undo)
6. If the bug is semantic (case B):
   - Verify what undo stack entries exist for: select → delete.
   - Confirm whether selection transitions are recorded as `edit_mode` ops.
   - Ensure the second undo corresponds to “undo selection” (i.e., `editingNoteId` becomes null), not some other entry.
7. Patch either:
   - client-side recording of edit-mode transitions, OR
   - server-side coalescing rules in `app/services/undo_state.py`,
   so the history is: [select/edit_mode] then [delete_subtree], enabling:
   - undo(delete) => note restored + selected
   - undo(edit_mode) => deselected

Success criteria:
- The new Cypress test passes.
- Manual repro matches expected behavior.


## Phase 4 — Regression Sweep
8. Run full Cypress suite.
9. Run `./sanitycheck/run`.

Success criteria:
- All tests pass and sanitycheck is clean.

