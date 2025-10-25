# PLAN: app/ Structure Cleanup and Consolidation

Goal: Normalize the app/ layout with Cmd-first usecases, unified security, and no routers inside services, while minimizing risk and churn. This plan is incremental and reversible.

## Constraints & Preferences
- Cmd as first-class: keep command pattern (Cmd*) as the usecase layer.
- No routers inside services: routers live under app/api/routes.
- Unify encryption into a dedicated security module (compat shims allowed).
- Fail fast: preserve existing fail-fast semantics; avoid soft fallbacks.
- Keep functionality working at each phase; small, verifiable steps.

## Target Structure (high level)

app/
- api/
  - routes/
    - notes.py        # from app/app.py (notes router only)
    - auth.py         # extracted from services/auth.py
    - memory.py       # extracted from services/memory.py
  - deps.py           # from api/dependencies.py
  - middleware/
    - auth.py         # from api/middleware.py
- usecases/           # Cmd* usecases (rename from endpoints/)
  - base.py           # QueryCommand
  - create_note.py, move.py, view.py, ... (all Cmd* files)
- services/           # pure application services (no APIRouter)
  - auth_service.py   # logic from services/auth.py (router moved out)
  - memory_service.py
  - note_service.py   # optional; see “Cmd vs Service” below
  - content_cache.py, transaction_manager.py, etc.
- security/
  - encryption.py     # unify services/encryption + utils/encryption public surface
  - tokens.py         # optionally move here from services/tokens.py
- db/
  - session.py        # unify models/database + db/engine helpers
  - schema.py, notes_sql.py, settings_sql.py
- domain/             # (optional) pure domain logic
  - linked_list.py, list_operations.py, entities.py, enums.py
- presentation/
  - templates/ (existing under app/templates)
  - renderers/ (e.g., render/note_renderer.py)
- main.py             # FastAPI app wiring, template lookup, router includes

Notes:
- Keep app/static and app/templates paths unchanged.
- Maintain existing API paths and behavior during the reorg.

## Phase Plan (incremental)

Phase 0 — Inventory & Mapping (no code changes)
- Document the current responsibilities of:
  - Cmd* in app/endpoints/* vs services/note_service.py
  - stores: services/note_store.py vs services/store.py
  - db layers: models/database.py vs db/engine.py
- Outcome: short matrix (who calls what; missing features in each store) to decide the canonical store.

Phase 1 — Router Extraction & Placement (low risk)
- Create app/api/routes/{notes,auth,memory}.py
  - Move the notes router out of app/app.py into routes/notes.py (keep only router; no business logic changes).
  - Extract APIRouter from services/auth.py and services/memory.py into routes/{auth,memory}.py.
  - Leave AuthService/MemoryService logic in services/{auth_service,memory_service}.py.
- Rename api/dependencies.py → api/deps.py; update imports.
- Move api/middleware.py → api/middleware/auth.py; update import in app/main.py.
- Success: app boots; endpoints respond; services files have no APIRouter.

Phase 2 — Cmd-first Usecases (rename endpoints → usecases)
- Rename app/endpoints/* → app/usecases/*; keep class names Cmd*.
- Update imports in routes/notes.py and other call sites to use app/usecases/*.
- Decide relationship to services:
  - Preferred: Cmd* orchestrates, delegating to services (NoteService) for DB ops.
  - Alternatively: fold NoteService methods directly into Cmd* where duplication exists.
- Success: All routes import Cmd* from app/usecases; tests/UX unaffected.

Phase 3 — Security Unification (encryption)
- Create app/security/encryption.py combining:
  - services/encryption.py (crypto core)
  - utils/encryption.py (token/DEK integration public surface)
- Keep a small shim in app/utils/encryption.py that re-exports from security/encryption.py for backward compatibility (until call sites are updated).
- Optionally move services/tokens.py to app/security/tokens.py; update imports.
- Success: login, encryption/decryption, and cache hydration work end-to-end.

Phase 4 — DB Session Unification
- Create app/db/session.py that houses SafeSession and helpers:
  - begin_writer, connect_reader, allow_reads, enable_read_guard, disable_read_guard
- Move/merge logic from models/database.py and db/engine.py (single source of truth).
- Update imports across codebase to use app/db/session.py.
- Success: startup sequence (schema init, read guard, cache + store hydration) completes; CRUD works.

Phase 5 — Template Lookup Centralization (minor)
- Provide a get_templates() factory (e.g., app/presentation/templates.py or app/core/templates.py).
- Replace ad-hoc TemplateLookup usage (e.g., services/memory.py) with the centralized factory.
- Success: memory endpoint renders with the main TemplateLookup; path hacks removed.

Phase 6 — Store Consolidation (highest risk; gated)
- Choose canonical store based on Phase 0 matrix (likely note_store.py due to cache integration) and add any missing APIs from the other store.
- Provide a temporary adapter so previous call sites (Cmd* and services) work without large diffs.
- Hydrate once at startup; ensure both view and service paths read from the same structure.
- Remove the deprecated store module after call sites are migrated.
- Success: single in-memory source of truth; view diff and Cmd* flows intact.

Phase 7 — Cleanup & Docs
- Delete dead modules after migrations (legacy paths, deprecations).
- Update docs/AI-SUMMARY.md to reflect new layout; add a short “Architecture quick ref”.
- Optional: add import-lint to prevent APIRouter usage in services/*.

## Acceptance Criteria
- All routes function as before: notes, auth, memory, polling, locks.
- No APIRouter in app/services/*.
- Encryption works (login, set/change/remove password); cache + store hydrate successfully.
- One DB session/guard implementation; no duplicated guard logic.
- A single canonical in-memory store backs both view and service flows.
- Cypress suite passes; manual smoke checks for CRUD + undo/redo + memory mode pass.

## Risks & Mitigations
- Store consolidation risk: introduce adapter layer; defer deletion until parity proven.
- Import churn risk: perform in small PR-sized commits per phase; run quick smoke after each step.
- Encryption refactor risk: keep a temporary shim (utils/encryption.py) for staged rollout.

## Rollback Strategy
- Each phase is commit-bounded; use git revert on the last phase commit only.
- Keep shims during transitions to allow quick backouts.

## Test & Verify (per phase)
1. Run server: `.venv/bin/python main.py` and hit key routes.
2. Quick manual flows: create/update/move/delete, undo/redo, login/logout, memory mode.
3. Optional: run Cypress (`./run_cypress_tests.sh`) once core refactors settle (Phases 1–4).

## Proposed Commit Slices
- Phase 1: “api: extract routers; move middleware/deps”.
- Phase 2: “usecases: rename endpoints to usecases; wire routers to Cmd*”.
- Phase 3: “security: unify encryption; add shim”.
- Phase 4: “db: unify SafeSession + helpers”.
- Phase 5: “presentation: centralize TemplateLookup”.
- Phase 6: “store: canonicalize + adapter; remove duplicate”.
- Phase 7: “cleanup + docs”.

## Open Items for Confirmation
- Canonical store: prefer services/note_store.py (cache-aware) as the base? If yes, I’ll extend it to cover any missing APIs used by Cmd*.
- Domain folder: are you comfortable with moving linked-list and entity logic under app/domain/? (Pure refactor, import updates only.)
- Move tokens service under security/? (Keeps auth concerns together.)

— End of plan —

