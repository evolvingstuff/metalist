# API2 Rollout Plan

Owner: server/platform
Status: Active migration
Goal: Reach feature parity on `/api2` so we can remove the legacy `/api` stack.

## Immediate Objectives (Blockers to removing v1)
1. ✅ **Auth parity** – `/api2/auth` now mirrors v1 (status/login/logout/password flows) and middleware enforces auth for API2 paths.
2. ✅ **Diff view parity** – `/api2/notes/view` returns filtered snapshots, emits real `updateUUID`s, and includes lock metadata.
3. ✅ **Clipboard** – Nested paste logic fixed; copied notes return HTML/plaintext for clipboard integration.
4. ✅ **Memory mode** – `/api2/memory` provides HTML payload, stats, and feedback flow.
5. **Housekeeping for v1 removal** *(in progress)*
   - Remove v1 router wiring once smoke tests pass against `/api2` only.
   - Audit frontend config so nothing points at `/api`.
   - Update docs / setup scripts for API2-only world.

## Supporting Work
- Add targeted tests (later) once manual validation confirms behavior.
- Capture manual test scripts/checklists while automated coverage is absent.
- Document new API2 endpoints in developer docs.

## Completion Criteria
- All API2 endpoints listed above functional and manually verified.
- Frontend operates solely against `/api2`.
- No runtime references to `/api` in codebase or configs.
- Legacy v1 modules safe to delete (track separately once parity verified).

## Notes / Decisions Log
- Full unit/integration test suites removed (manual testing for now). Cypress UI tests retained.
- Drag/drop "create-drop" flow intentionally removed from both v1 and v2.
- Undo/redo + clipboard fixes already merged; keep eye on regression coverage once tests return.

## Next Step
→ Execute housekeeping tasks to detach `/api` (router removal, config audit, docs update), then plan v1 code deletion.
