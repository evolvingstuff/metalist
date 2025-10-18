# ORM Sunset Plan

## Motivation
We now maintain an authoritative in-memory `NoteStore`, emit direct SQL for writes, and enforce a post-startup read guard. SQLAlchemy’s ORM layer no longer adds value—it only forces hidden SELECTs, complicates undo/redo event hooks, and risks reintroducing reads that crash the server. Replacing the ORM with explicit SQL/core utilities will simplify the stack, harden the guard, and keep intent obvious.

## Objectives
1. Remove ORM dependencies from request handlers, services, and undo/redo.
2. Provide a minimal SQL helper layer (using SQLAlchemy Core or raw SQL) that the services call explicitly.
3. Preserve existing behaviour (CRUD, move, collapse, undo/redo) while keeping the read guard active.
4. Clean up legacy event hooks and session usage so the codebase no longer relies on ORM side effects.

## Plan
1. **Inventory & Design**
   - Catalogue current ORM usage (Query, `.get()`, event hooks, flush semantics, session lifecycle).
   - Decide on helper abstractions (e.g. `db_select`, `db_update_links`, `db_insert_note`). Document them next to `NoteStore`.
   - Outline undo/redo state capture using `NoteStore` snapshots instead of SQLAlchemy events.

2. **Infrastructure**
   - Introduce a thin SQL helper module using SQLAlchemy Core or raw SQL with parameter binding.
   - Provide explicit transaction wrappers where needed (mirroring current service contexts).
   - Ensure helpers respect the read guard (read helpers call `SafeSession.allow_reads`).

3. **Read Paths**
   - Replace remaining ORM reads with store lookups or explicit SQL helpers (e.g., auth settings, maintenance jobs).
   - Remove fallback ORM code paths already covered by `NoteStore`.

4. **Write Operations**
   - Update note CRUD, move, collapse, delete, and related services to use the helper functions exclusively.
   - Ensure data mutations update both the database and `NoteStore` in one place.

5. **Undo/Redo Refactor**
   - Build note-diff snapshots directly from `NoteStore` before/after each operation.
   - Update `Command` objects to replay mutations via the helper functions and store APIs (no ORM events).

6. **Session & Guard Cleanup**
   - Strip ORM-specific configuration (`sessionmaker`, events) that are no longer needed.
   - Simplify `SafeSession` to handle connection management for the helper layer.

7. **Testing & Validation**
   - Regression test manual flows (CRUD, move, collapse, undo/redo, auth password flows).
   - Verify guard behaviour by attempting to execute raw SELECTs outside `allow_reads`.
   - Add targeted unit/integration tests for the SQL helper functions and undo diff logic.

8. **Documentation & Cleanup**
   - Update developer docs / design notes describing the new data access approach.
   - Remove legacy files or comments referencing ORM event hooks.

## Risks / Watchouts
- Undo/redo correctness must be revalidated after the new diff mechanism.
- Auth-related flows still need controlled reads; ensure `allow_reads` is scoped tightly.
- Migration should be incremental to avoid large unreviewable changes—commit per subsystem.
