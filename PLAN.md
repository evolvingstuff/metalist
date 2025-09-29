# PLAN: Refactor Undo/Redo Fuzz Test

## Goals
- Drive the fuzz harness through NoteService (or API helpers) so it respects integrity checks and encryption.
- Preserve coverage of randomized operations (add, delete, move) while using the official service layer.
- Keep undo/redo exercised under the new guardrails without relying on `xfail`.

## Tasks
1. **Analyze Current Harness**
   - Map each direct LinkedListManager/DB mutation to the equivalent NoteService call.
   - Identify any helper gaps (e.g., drag/drop semantics) and plan abstraction.

2. **Introduce Service-Based Helpers**
   - Wrap NoteService operations (create/move/delete) with concise utility functions for the fuzz test.
   - Ensure client IDs and transaction managers are wired correctly per operation.

3. **Update Fuzz Loop**
   - Replace direct database mutations with the new helpers.
   - Maintain existing randomization logic but adapt outcome asserts to new responses.
   - Capture errors from service layer and retry/skip as appropriate.

4. **Handle Undo/Redo Calls**
   - Ensure undo/redo use the same client ID and service stack, respecting encryption.
   - Confirm integrity checks remain active (dev flag can be optional).

5. **Validation**
   - Run the fuzz test standalone until stable; adjust operations if persistent failures occur.
   - Run full test suite to confirm no regressions.

6. **Cleanup**
   - Remove temporary `xfail` and document the new helper functions.
   - Delete PLAN.md when feature completes.

## Deliverables
- Updated fuzz harness using NoteService.
- Passing test suite without xfails.
- Optional README note documenting how to run the fuzz test.
