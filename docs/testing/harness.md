# Testing Status

The legacy unit/integration suites were removed during the API2
migration. Manual regression passes plus the Cypress UI suite now
cover the project.

There is targeted JS unit coverage for external HTML paste sanitization:

- `tests/unit/html_paste_sanitizer_service.test.mjs`
- Run with: `node --test tests/unit/html_paste_sanitizer_service.test.mjs`

For deterministic Cypress runs, the server exposes a TEST_MODE-only reset
endpoint: `POST /api2/test/reset`.

That reset now clears all state the Cypress suite is allowed to assume away:

- notes + app settings tables
- search interaction history
- view cache
- tab-state store
- issued auth tokens
- in-memory sync state in `app/services/sync.py` including note locks and
  server clipboard contents

The Cypress harness also enforces a browser-side clean boot for every spec:

- `cypress/support/e2e.js` calls `cy.resetTestState()` before each test
- `cypress/support/commands.js` clears cookies/localStorage/sessionStorage in
  `cy.resetTestState()`
- `cy.visitApp(...)` clears browser storage again before navigation and waits
  for both:
  - `body` to not have class `loading`
  - `body[data-app-ready="true"]`

`app/static/js/main.js` sets `data-app-ready="true"` only after
`Auth.init()`, `ModeManager.init()`, and `CommandPalette.init()` finish and
the main app has been revealed. This prevents Cypress from racing event-handler
registration during startup.

## Deterministic Cypress Rules

Every new Cypress spec must follow these rules:

- Build all required notes, search state, clipboard state, selection state,
  and auth/tab context inside that spec. Never rely on a prior spec.
- Use `cy.visitApp('/')` instead of raw `cy.visit('/')` so the test waits for
  the real app-ready boundary.
- If a shortcut depends on focus, explicitly establish the correct focus target
  first and assert it when needed.
- If a shortcut would be swallowed by the wrong element after a refresh
  (for example the search input), click the intended surface before typing.
- If the behavior under test is not the click/shortcut transport itself, prefer
  deterministic setup via authenticated `cy.request(...)` and then assert the
  current UI outcome after reload.
- A spec must pass no matter where it lands in a randomized full-suite order.

Run headless UI tests via `./run_cypress_tests.sh` (starts the server with
`TEST_MODE=1`, then runs `npx cypress run`).

If we decide to rebuild automated backend coverage, treat this file as
the starting point for a new plan.

## Ontology

Ontology rules are DB-backed and editable via the UI/API. Unit coverage lives in:

- `tests/unit/test_ontology_rules_store_sqlite.py`

See `docs/design/ontology-rules-v1.md`.
