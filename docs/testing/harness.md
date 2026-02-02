# Testing Status

The legacy unit/integration suites were removed during the API2
migration. Manual regression passes plus the Cypress UI suite now
cover the project.

For deterministic Cypress runs, the server exposes a TEST_MODE-only reset
endpoint: `POST /api2/test/reset`.

Run headless UI tests via `./run_cypress_tests.sh` (starts the server with
`TEST_MODE=1`, then runs `npx cypress run`).

If we decide to rebuild automated backend coverage, treat this file as
the starting point for a new plan.

## Ontology

Ontology rules are DB-backed and editable via the UI/API. Unit coverage lives in:

- `tests/unit/test_ontology_rules_store_sqlite.py`

See `docs/design/ontology-rules-v1.md`.
