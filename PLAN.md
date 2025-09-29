# Test Coverage Expansion Plan

## Context
- Current pytest suite focuses on low-level linked-list utilities, note CRUD helpers, toggle collapse, undo/redo (plain + encrypted).
- End-to-end coverage limited to four Cypress specs targeting basic item creation and caret behavior; no authentication, search, or sync coverage.
- No FastAPI integration tests (TestClient) and few regression-focused cases for previously fixed issues (integrity guards, password removal, maintenance mode).

## Goals
1. Increase confidence in note lifecycle, undo/redo, sync, and auth flows via layered tests.
2. Catch regressions quickly by codifying past bugs and high-risk scenarios.
3. Provide measurable coverage signals (pytest + Cypress) to guide future work.

## Workstreams

### 1. Coverage Baseline & Infrastructure
- Add `pytest-cov` config + `coverage.xml` generation; document command in README.
- Introduce helper fixtures for authenticated FastAPI client and seeded databases (reuse `tests.unit.common.db`).
- Evaluate speed hotspots; mark long-running tests with `@pytest.mark.slow` and add opt-in flag.

### 2. Service-Level & Unit Tests
- `NoteService`: cover error paths (invalid parent/sibling, collapse idempotency, search auto-population, delete empty list flag).
- `SyncState`/`content_cache`: tests for clipboard storage, UUID churn, cache warmup, lock expiry.
- `AuthService`/`tokens`: exercise password set/reset, token TTL expiry, invalid token cleanup.
- `MaintenanceMode` and `IntegrityGuard`: ensure toggles & guard exceptions behave (esp. `DEV_ENFORCE_INTEGRITY_CHECKS`).
- Property-style invariants for linked-list operations (Hypothesis strategies around move/create/delete sequences) extending fuzzers beyond undo-only flows.

### 3. API Integration Tests (FastAPI TestClient)
- Authentication flow: password setup, login, token refresh, unauthorized access rejection.
- Notes API: CRUD, move, toggle collapse, search auto-population, deletion of subtrees with `all_deleted` flag validation.
- Undo/Redo endpoints: ensure command stacks mutate correctly and return expected payloads.
- Sync endpoints: clipboard, sync UUIDs, lock acquisition/release, concurrent client edge cases.
- Integrity & maintenance: `/api/dev` guard routes when enabled/disabled.

### 4. Regression Scenarios from Past Bugs
- Password removal regressions (`tests/unit/test_password_removal.py`) expansion: ensure tokens revoked, auth middleware reflects state.
- Integrity guard failure reproduction to ensure proper crash when invariants break.
- Search highlighting note creation to avoid blank content or missing markers.
- Clipboard and sync race: ensure sequential requests yield distinct UUIDs and persist clipboard contents.

### 5. Frontend E2E (Cypress)
- Auth happy path + lockout (seed backend, assert login gating).
- Note hierarchy operations: drag/drop reorder, create child/sibling, collapse persistence across reload.
- Undo/redo UI feedback: ensure UI state matches backend after sequence.
- Search flow: perform text search, verify filtered list & auto-populated note content when adding new note during search.
- Sync/conflict indicators (if UI exposes) or clipboard copy/paste interactions.

### 6. Tooling & CI Hooks
- Update Cypress configuration to run headless in CI and capture screenshots/videos on failure.
- Integrate coverage thresholds into CI (fail build if pytest coverage < target, e.g., 85% for services).
- Document test matrix (`pytest`, `pytest --cov`, `npm run test:ui`) in README or CONTRIBUTING.

## Deliverables
- New/updated pytest modules under `tests/unit` and `tests/integration` (new package).
- New Cypress specs under `tests/ui/cypress/e2e` plus shared helpers.
- Coverage tooling (`coverage.xml`, README updates).
- Regression test docs linking each test to historical issue (inline comment or doc section).

## Open Questions for User
1. Desired minimum coverage thresholds (overall and/or critical modules)?
2. Should headless UI tests run in CI on every push or only on main?
3. Any upcoming features or bug classes we should prioritize for regression cases?
