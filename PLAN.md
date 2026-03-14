# Namespace DB Selection Plan

## Goal
- Add launch-time namespace support so one MetaList process can target a different SQLite database by name.
- Keep namespaces strictly process-scoped: one process, one namespace, one notes DB, one derived files DB.
- Keep port selection orthogonal to namespace selection.

## Non-Goals
- No multi-namespace support inside a single running process.
- No namespace columns, schema changes, or per-request namespace routing.
- No inference from port numbers.

## Proposed Behavior
- `python main.py` keeps the current legacy default database path unchanged.
- `python main.py --namespace work` uses a namespaced notes DB basename:
  - notes DB: `~/MetaList/work.metalist.db`
  - files DB: `~/MetaList/work.metalist.files.db`
- The files DB continues to be derived from the chosen notes DB path, so no separate file-DB namespace logic is needed.
- The integrated MCP server continues to use the same in-process app state, so it automatically follows the selected namespace.
- The MCP client / agent sidecar remains URL-based rather than namespace-aware.
- Namespace values must be a simple slug: lowercase letters, digits, and `-` only.
- Invalid namespace values fail at startup.

## Compatibility Rules
- Existing no-namespace startup remains backward-compatible with the current default DB path.
- `--port` and `--https-port` remain independent startup options and do not affect namespace resolution.
- `--test` / `TEST_MODE=1` keeps current isolated test behavior.
- Conflicting startup modes should fail fast instead of silently choosing one:
  - namespace + test mode
  - invalid namespace syntax

## Implementation Plan
1. Add a small startup-argument parser that runs before `app.main` is imported.
   - Support `--namespace`.
   - Preserve existing `--test`.
   - Wire CLI port flags into the same early startup path so the launch flow stays consistent.
2. Introduce a shared runtime resolver for startup configuration.
   - Validate namespace syntax.
   - Resolve the effective notes DB path.
   - Keep the legacy default path when no namespace is supplied.
   - Expose the resolved DB path through a single explicit config input so import-time consumers read the same value.
3. Refactor `app/config.py` to use the shared DB-path resolver instead of hardcoding only `metalist2.db` vs `test.db`.
   - Keep fail-fast behavior for conflicting inputs.
   - Keep direct env-based startup usable for non-`main.py` entrypoints.
4. Update `main.py` startup order.
   - Parse CLI args first.
   - Resolve namespace + port inputs.
   - Export the resolved settings needed by import-time config.
   - Import `app.main` only after startup config is finalized.
   - Ensure the auto-started MCP agent sidecar receives the effective MCP URL for the resolved main-app port instead of assuming `127.0.0.1:8000`.
5. Audit secondary entrypoints that depend on `app.config.DATABASE_URL`.
   - `convert-from-legacy.py` should resolve the same target DB selection rules instead of drifting from `main.py`.
   - Review standalone `mcp_client.py` behavior and keep it URL-driven; do not add namespace semantics there unless a concrete use case appears.
6. Add targeted unit tests.
   - Namespace validation accepts valid slugs and rejects dots, slashes, spaces, uppercase, and empty strings.
   - Default startup still resolves to the current legacy DB path.
   - Namespaced startup resolves to `<namespace>.metalist.db`.
   - Files DB derivation still yields `<namespace>.metalist.files.db`.
   - Conflicting test-mode/namespace inputs fail loudly.
   - Runtime startup config continues to handle port and TLS settings correctly.
7. Update docs after implementation.
   - `README.md` launch examples
   - `docs/AI-SUMMARY.md` startup/config notes
   - MCP launch notes where sidecar/default MCP URL behavior changes

## Verification
- Run focused pytest coverage for runtime/config/file-path behavior.
- Run any broader startup-related tests that touch `main.py`, `app/config.py`, or file DB path derivation.
- Run `./sanitycheck/run` if present once implementation is complete.

## Risks To Watch
- `app.config` is import-time configuration, so startup order matters.
- Any script importing `app.config.DATABASE_URL` can diverge if it does not share the same resolver.
- The sidecar currently defaults to a hardcoded MCP URL, so namespace work must not leave MCP pointing at the wrong port.
- Backward compatibility for the existing default DB path must remain intact.
