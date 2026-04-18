# Testing Status

The legacy unit/integration suites were removed during the API2
migration. Current coverage is a mix of Python/unit tests, small JS unit
tests, startup sanity gates, and manual regression passes.

There is targeted JS unit coverage for external HTML paste sanitization:

- `tests/unit/html_paste_sanitizer_service.test.mjs`
- Run with: `node --test tests/unit/html_paste_sanitizer_service.test.mjs`

For deterministic browser automation, the server still exposes a
`TEST_MODE`-only reset endpoint: `POST /api2/test/reset`.

That reset clears all state a browser harness is allowed to assume away:

- notes + app settings tables
- search interaction history
- view cache
- tab-state store
- issued auth tokens
- in-memory sync state in `app/services/sync.py` including note locks and
  server clipboard contents

`app/static/js/main.js` sets `data-app-ready="true"` only after
`Auth.init()`, `ModeManager.init()`, and `CommandPalette.init()` finish and
the main app has been revealed. Any future browser harness should wait on
that boundary instead of racing startup.

## Current Direction

As of 2026-04-08, the Cypress harness was removed because it was costing more
time than it was saving. If browser automation is reintroduced later:

- start with a very small smoke suite
- keep shared interaction logic covered below the browser layer
- treat full-browser coverage as optional confidence testing, not the primary
  debugging loop

## Ontology

Ontology rules are DB-backed and editable via the UI/API. Unit coverage lives in:

- `tests/unit/test_ontology_rules_store_sqlite.py`

See `docs/design/ontology-rules-v1.md`.
