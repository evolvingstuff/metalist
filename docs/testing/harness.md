# Testing Harness Migration Notes

The unit-test suite still targets the old SQLAlchemy stack. Until the
fixtures and helpers are rewritten, `pytest` fails during collection.

## Current Failure Mode
- `tests/unit/common.py` imports `Base`, `DBNote`, and `SessionLocal`
  from `app.models.database`. Those symbols were removed when we
  switched to the guard-aware sqlite layer, so every test that imports
  `tests.unit.common` crashes before it can run.
- Many tests still rely on ORM behaviors (`session.add`, `query()`,
  `.filter`, `.delete`, etc.). The sqlite helpers expose direct
  parameterized SQL instead, so the tests must be adapted.

## Porting Plan
1. **Rewrite the shared fixture.**
   - Create a `SafeSession`-backed helper that initializes an in-memory
     sqlite database via `initialize_schema`.
   - Provide context managers that mirror the old `transaction_scope`
     but call `session.commit()` / `session.rollback()` directly.

2. **Introduce helper wrappers.**
   - Add small utilities inside `tests/unit/common.py` that emulate the
     handful of ORM features the tests need (e.g., `fetch_note`,
     `delete_all_notes`, ordered child queries) using the new
     `notes_sql` functions.

3. **Audit individual tests.**
   - Replace calls like `db.add(DBNote(...))` with the appropriate
     helper (e.g., `insert_note` plus cache updates).
   - Swap `.query(...).filter(...)` usages for helper calls that rely on
     `LinkedListManager` or the sqlite helpers.

4. **Update hypothesis strategies & fixtures.**
   - The hypothesis-based tests build notes through direct ORM access.
     They need to call the same helper layer to stay in sync.

5. **Verify undo/redo expectations.**
   - Re-run the property-based suites to ensure the new diff/snapshot
     approach still satisfies the invariants that were being checked via
     the ORM objects.

## Interim Status
- Manual smoke tests confirm CRUD, move, collapse, undo/redo, and
  authentication flows over the sqlite stack.
- `pytest` remains red until the items above are addressed.

Keep this document up to date as the test harness is migrated.
