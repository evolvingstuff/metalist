# PLAN: Fix Critical Issues from Review

## Goals
- Remove dead sync-state module and prevent import errors.
- Ensure encryption utilities fail fast instead of silently degrading security.
- Correct API bugs uncovered in the review (e.g., undefined `request`).
- Keep cache refresh and related flows crash-on-failure compliant.
- Restore password modal usability so users can type credentials.
- Validate the fixes with targeted tests.

## Tasks
1. **Clean Up Legacy Sync Module**
   - Delete `app/services/sync_service.py` and confirm no remaining references.

2. **Fix Notes API Bug**
   - Update `create_note_with_position` to use `command.clientId` when acquiring the note service.
   - Scan nearby endpoints for similar issues.

3. **Harden Encryption Utilities**
   - Update `encrypt`, `decrypt`, `set_encryption_key`, and `get_encryption_status` to raise on internal failures.
   - Ensure callers handle the stricter failure behavior (especially auth/login and note creation flows).

4. **Enforce Fail-Fast Cache Refresh**
   - Make `refresh_encrypted_cache` re-raise errors so failures surface immediately.
   - Audit callers to ensure they handle the raised exceptions correctly.

5. **Regression Checks**
   - Run targeted unit tests (`tests/unit`) and adjust as needed.
   - Perform quick manual reasoning around login and note creation flows if automated coverage is lacking.

6. **Fix Password Modal Input Handling**
   - Allow keyboard events to reach password modal form fields instead of being globally blocked.
   - Verify typing works in the modal while shortcuts remain suppressed elsewhere.

7. **Reduce Idle Auth Polling Noise**
   - Throttle `/api/auth/sessions` refreshes so we only hit the endpoint after real activity with a minimum interval.
   - Confirm background sync (`/api/notes/check-updates`) still runs as expected.

8. **Fix Auth Headers on Note Lock Heartbeat**
   - Send the bearer token with `/api/notes/acquire-lock` requests so authenticated sessions don’t get 401s while editing.
   - Handle 401 responses by exiting edit mode and surfacing an auth warning.

## Deliverables
- Updated code reflecting the fixes above.
- Test results or rationale for any skipped tests.
