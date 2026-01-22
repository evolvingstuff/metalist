# PLAN

## Goal
Fix the undo bug:

- Select note
- Cmd-Del to delete
- Cmd-Z to undo (note reappears)
- Cmd-Z to undo (note should be deselected, but remains selected)

…while enforcing the intended invariant:

- The client must never allow a second user command to execute while a prior server-bound command is in-flight.
- Extra inputs during in-flight are ignored/dropped.
- NO queuing/coalescing/replay of user commands.
- Background traffic (heartbeat/polling/infinite-scroll refresh) must not run while a user command is in-flight.


## Why Phase 2 Comes First
Historically, “Phase 1 repro test first” was unreliable because there is no single authoritative command gate today:

- Not every server-bound UI action is serialized behind one busy flag.
- Some background loops can issue network calls independently.

This makes undo behavior appear timing-dependent even when the user is not “pressing fast”, because unrelated background calls can interleave with user commands and/or transiently trip the “busy” condition.

So we first make the client deterministic (Phase 2), then add the failing Cypress repro (Phase 1).


## Non-Goals
- Do not introduce queued/coalesced command behavior.
- Do not change existing Cypress specs.


## Phase 2 — Enforce a Single Command Gate (Drop Inputs While In Flight)
1. Implement a single client-side command gate (mutex) with a tiny API:
   - `CommandGate.run(name, asyncFn)`
   - `CommandGate.isBusy()`
   - It must set/unset the busy flag in a `finally`.
   - It must NEVER queue or replay commands.
2. Route ALL user-initiated server-bound actions through the gate:
   - Delete, undo/redo, create, move, edit-mode transitions, save.
   - Ensure click handlers don’t “fire and forget” async actions without going through the gate.
3. Update keyboard/mouse handlers:
   - If gate busy: drop the input and return immediately.
   - (Optional) log one structured “dropped input” event for diagnosis.
4. Stop background traffic while gate busy:
   - Polling/heartbeat: skip ticks while `CommandGate.isBusy()`.
   - Infinite scroll: skip polling while `CommandGate.isBusy()`.
   - Any other periodic refresh must be similarly blocked.

Success criteria:
- DevTools Network shows at most one in-flight *user command* request at a time.
- Heartbeats/refreshes do not fire during a user command.
- Inputs during in-flight are dropped (not queued).


## Phase 1 — Cypress Repro (Now Deterministic)
5. Add a new Cypress spec that reproduces the bug without relying on “pressing fast”.
   - Drive Cmd-Z twice with an explicit wait for the gate to be idle between presses.
   - Assert that the note is not in editing state after the second undo.
6. If needed, add minimal temporary instrumentation to help debug ordering (remove once fixed).

Success criteria:
- The new spec fails against current semantics and passes after the fix.


## Phase 3 — Fix Undo Semantics (Deselect on 2nd Undo)
7. Verify undo stack entries for: select → delete.
   - Confirm whether selection transitions are recorded as `edit_mode` ops.
   - Ensure the second undo corresponds to “undo selection” (i.e., `editingNoteId` becomes null).
8. Patch either:
   - client-side recording of edit-mode transitions, OR
   - server-side coalescing rules in `app/services/undo_state.py`,
   so the history is: [select/edit_mode] then [delete_subtree], enabling:
   - undo(delete) => note restored + selected
   - undo(edit_mode) => deselected

Success criteria:
- Manual repro matches expected behavior.
- Cypress spec passes.


## Phase 4 — Regression Sweep
9. Run full Cypress suite.
10. Run `./sanitycheck/run`.

Success criteria:
- All tests pass and sanitycheck is clean.
