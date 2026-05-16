# TODO

## Atomicity / Consistency Follow-Ups

### 1. Fix in-memory store divergence on rolled-back aggregate commands

**Priority:** High

Several server-side aggregate commands are now correctly one HTTP request and one DB transaction, but their helper calls mutate the in-memory `NoteStore` before the outer request transaction commits. If a later step in the same command raises, SQLite rolls back, but the already-mutated process cache can remain ahead of the database until restart or rehydration.

Examples:
- `app/usecases/split_note.py`: updates the original note, inserts siblings, then records undo.
- Similar pattern may exist anywhere a `Cmd*` calls multiple `apply_*` helpers under `@transactional_route`.

Failure mode:
- DB transaction rolls back correctly.
- In-memory store/search index may already reflect partial updates.
- Subsequent snapshots can be built from stale/wrong in-memory state even though persisted DB state is clean.

Likely fix direction:
- Add an after-commit hook mechanism to `app/db/session.py` request transactions.
- Change mutating helpers so DB writes happen inside the transaction and store/search-index mutations are registered as after-commit callbacks.
- On rollback, callbacks must be discarded.
- For non-request standalone writers, preserve current behavior by running callbacks after the local commit succeeds.

Success criteria:
- A deliberate exception after the first mutation in `CmdSplitNote` leaves both DB and `NoteStore` unchanged.
- Unit test covers rollback behavior for at least one multi-step command.
- Existing route transaction audit still passes.

### 2. Make file attachment atomic enough for user intent

**Priority:** Medium

Current file attach flow is client-orchestrated:
1. Upload file via `POST /api2/files/upload`.
2. Possibly create/select a target note.
3. Insert `![[file-id]]` into the editor DOM.
4. Save the note content.

Relevant client code:
- `app/static/js/modules/mode-manager/services/file-reference-service.js`

Failure modes:
- Upload succeeds, then note save fails: file row exists but no note references it.
- If attach creates a new note first and a later save fails, a blank note can remain.
- Undo does not treat "attach file reference to note" as one user-level operation.

Likely fix direction:
- Add a server endpoint/use case for "attach uploaded file reference to note content" or a broader endpoint that uploads and inserts in one transaction where feasible.
- If upload must remain separate because multipart + note edit details are awkward, make cleanup explicit: delete the uploaded file on downstream failure when safe, or mark uploads pending until first successful note reference save.
- Ensure undo/redo sees the note content change as one operation.

Success criteria:
- Failed attach cannot leave a newly created blank note plus unreferenced file as the visible result of one user action.
- Unreferenced uploaded files are either cleaned immediately on failure or deliberately classified as pending/trim-safe.

### 3. Review create-note while editing as a multi-step UX action

**Priority:** Low

Creating a note while editing currently does:
1. Save current note if edited.
2. Create sibling/top/child note.
3. Switch selection/edit mode to the new note.

Relevant code:
- `app/static/js/modules/mode-manager/actions/note-actions.js`
- `app/static/js/modules/mode-manager/actions/selection-actions.js`

This is less severe because saving the current note is a legitimate independent action, and note creation itself is already one server command. The residual issue is that the visible user action "create note and start editing it" can be interrupted after creation but before edit-mode bookkeeping.

Likely fix direction:
- Decide whether edit-mode tracking should be best-effort UI state or a strict persisted undo boundary.
- If strict, add a server command that creates the note and records/returns the intended edit-mode transition together.

Success criteria:
- A failure during post-create selection/edit-mode recording does not create confusing undo history or require extra undo presses.
