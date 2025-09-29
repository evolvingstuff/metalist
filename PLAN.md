# PLAN: Integrity Enforcement & Error Surfacing

## Goals
- Fail fast (dev-only) when note graph integrity breaks after writes.
- Assert note counts stay stable for operations that shouldn’t add/delete, and enforce expected deltas when they should.
- Introduce aggressive assertions throughout write paths to catch impossible states (all hard failures).
- Surface heartbeat/token refresh failures to the UI via the existing ErrorHandler.
- Keep all write endpoints atomic (rollback on failure) while adding integrity gates.

## Tasks
1. **Config Toggle**
   - Add `DEV_ENFORCE_INTEGRITY_CHECKS` (default False) in `app/core/config.py`.
   - Provide helper to query the flag where needed.

2. **Service Integrity Guards & Assertions**
   - In `NoteService` and other write services, capture note count before mutation when guard enabled.
   - After commit, verify note counts and pointer integrity via `ListTraversal.validate_list`.
   - Throw `RuntimeError` on any mismatch; ensure rollback occurs via context manager.
   - Sprinkle explicit assertions documenting invariants (e.g., command has client_id, counts align, UUIDs present).

3. **Linked List Validation Helper**
   - Create shared function (e.g., in `app/services/validation.py`) to run validations with readable error messages.
   - Optionally include more detailed diagnostics (first broken node) to aid debugging.

4. **Client-Side Error Surfacing**
   - Route heartbeat failures in `mode-context.js` through `ErrorHandler.handleApiError`.
   - In `polling-service.js`, forward non-OK responses from `/api/auth/sessions` to the error handler.
   - Ensure dev console logs remain for debugging.

5. **Tests / Manual Verification**
   - Update or add unit tests exercising `NoteService` integrity guard logic (using a dev-flag override).
   - Manually confirm UI shows banners when heartbeat/token refresh fails.

6. **Cleanup**
   - Document new config in README (optional) or inline comment.
   - Remove PLAN.md once feature complete.

## Deliverables
- Updated backend with dev-only integrity gates and strict count validation.
- Frontend changes that surface server errors immediately.
- Tests proving guards fire (and rollback) when data corruption is detected.
