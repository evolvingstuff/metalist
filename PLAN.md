# PLAN

## Goal
Eliminate “UI locks” caused by leaked loading/busy state, and make undo/redo boundaries explicit and predictable.


## Problems We’re Fixing
1. **UI hard-freeze**
   - Global keyboard handler drops all input while `ModeContext.isLoading` is true.
   - If any async path forgets to clear loading, the UI becomes permanently non-interactive.

2. **Too many global invariants scattered across the client**
   - Multiple independent loops: polling, infinite-scroll, tab-state persistence, undo/redo, view refresh.
   - Each has its own early-return rules, so it’s easy to miss a “clear loading” or “skip while busy”.

3. **Undo stack scope is unclear for global operations**
   - Bulk/global operations (expand/collapse all, command palette actions, etc.) can create huge undo histories or mix unrelated contexts.
   - Desired behavior: global view-changing operations should reset undo/redo, not be undoable step-by-step.


## Success Criteria
- It is impossible (or extremely difficult) for the UI to remain stuck in a “loading” state.
- Background traffic never runs during a user command.
- Undo/redo boundaries are explicit and deterministic:
  - Opening the Cmd+/ command palette resets undo/redo history.
  - Global actions (expand all / collapse all / similar) reset undo/redo history.
  - No bulk action can generate tens-of-thousands of undo entries.


## Non-Goals
- Don’t add “helpful” fallbacks; internal invariant violations should crash loudly.
- Don’t add queued/coalesced command behavior for user commands.


## Phase 1 — Inventory and Normalize Entry Points
1. Inventory **all server-bound user actions** and ensure each goes through a single boundary wrapper.
   - Create / save / delete / move / collapse / expand / undo / redo.
2. Inventory **all background request loops**.
   - Polling service, infinite scroll, tab-state persistence, any other timers.

Deliverable:
- A checklist of entry points and which wrapper they use.


## Phase 2 — Single Client Command Gate
3. Implement a single client-side gate with a small, strict API:
   - `CommandGate.run(name, asyncFn)`
   - `CommandGate.isBusy()`
   - No queueing: if busy, inputs are dropped.
4. Route all user-initiated server-bound actions through `CommandGate.run(...)`.
5. Block background traffic while `CommandGate.isBusy()`.

Deliverable:
- One authoritative “busy” source-of-truth.
- DevTools Network: never more than one in-flight *user command* request.


## Phase 3 — Make Loading State Un-leakable
6. Replace ad-hoc `setLoading(true/false)` patterns with a single helper that cannot leak.
   - Prefer a `.finally(...)` wrapper (JS sanitycheck forbids `try` without `catch`).
   - Add an invariant that loading can only be enabled/disabled by this helper.
7. Add a watchdog:
   - If loading remains enabled past a threshold, throw with the last known loading reason.

Deliverable:
- UI can’t remain “stuck” without a loud crash and a clear reason.


## Phase 4 — Define Undo/Redo Boundaries (Global Reset Semantics)
8. Add an explicit client-side undo boundary token (epoch) that is included in the `undoContext`.
9. On boundary events, bump the epoch:
   - Cmd+/ command palette open.
   - Expand all / collapse all.
   - Any other “global view change” action we agree is non-undoable.
10. Ensure bulk endpoints reset server-side undo stack at the start of execution (so they never append per-note ops).

Deliverable:
- Global actions never create massive undo histories.
- Undo/redo after a boundary returns `noop`.


## Phase 5 — Cypress Regression Suite Additions
11. Add/keep focused Cypress specs:
   - Selection/deselect undo returns to “none selected”.
   - Cmd+/ boundary: after opening palette, undo is `noop`.
   - Expand all / collapse all boundary: undo is `noop`.
12. Run full Cypress suite.
13. Run `./sanitycheck/run`.


## Notes / Open Questions
- Which other actions besides expand/collapse-all should be “global boundary” actions?
  - Examples to decide: reset view filters, reset all preferences, tab creation/deletion, etc.
