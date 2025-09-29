# PLAN: Fix Critical Issues from Review

## Goals
- Remove dead sync-state module and prevent import errors.
- Ensure encryption utilities fail fast instead of silently degrading security.
- Correct API bugs uncovered in the review (e.g., undefined `request`).
- Keep cache refresh and related flows crash-on-failure compliant.
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

## Deliverables
- Updated code reflecting the fixes above.
- Test results or rationale for any skipped tests.
