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
     - **Current ORM surface area (2024-?? audit):**
       - `app/models/database.py`: owns `SafeSession` subclass, `SessionLocal`, declarative models (`DBNote`, `AppSettings`), guard-aware `Session.execute`, startup helpers (`Base.metadata.create_all`).
       - `app/models/api_transaction.py`: registers global SQLAlchemy event listeners to capture undo/redo + cache hooks; relies on ORM instrumentation and `DBNote` instances.
       - Linked-list stack (`app/models/note_crud.py`, `list_operations.py`, `list_traversal.py`, `linked_list.py`, `note_crud` fallbacks, `models/utils.py`, `undo_redo.py`): heavy use of `db.query`, `db.get`, `db.add/delete`, `flush`, and direct attribute mutation on ORM entities for CRUD/move/copy/undo flows.
       - Service layer (`app/services/note_service.py`, `query_service.py`, `undo_service.py`, `integrity.py`, `auth.py`, `content_cache.py`, `note_store.py`, `memory_service.py`): depends on ORM sessions for reads, writes, guard snapshots, cache hydration, password flows, and render pipelines.
       - API/startup (`app/api/dependencies.py`, `app/api/notes.py`, `app/api/auth.py`, `app/api/dev.py`, `app/main.py`): inject `Session`, call `.query()`, `db.get()`, and rely on ORM metadata during app boot and admin utilities.
       - Tests/tooling (`tests/**`, `lorem_ipsum.py` helpers): create engines, call `.query()/.delete()`, and expect ORM semantics during fixtures and fuzzers.
   - Decide on helper abstractions (e.g. `db_select`, `db_update_links`, `db_insert_note`). Document them next to `NoteStore`.
   - Outline undo/redo state capture using `NoteStore` snapshots instead of SQLAlchemy events.

2. **Infrastructure**
   - Introduce a thin SQL helper module using SQLAlchemy Core or raw SQL with parameter binding.
   - Provide explicit transaction wrappers where needed (mirroring current service contexts).
   - Ensure helpers respect the read guard (read helpers call `SafeSession.allow_reads`).
   - **Proposed helper layout:**
     - `app/db/engine.py`: owns Engines (file + memory), exposes `get_writer()` / `get_reader()` yielding a guard-aware `Connection` wrapper that blocks `SELECT` unless inside `allow_reads`. Replaces `SafeSession`/`SessionLocal` with `GuardedConnection` context managers (“begin_write”, “allow_reads”).
     - `app/db/schema.py`: defines SQLAlchemy Core `MetaData`, `notes_table`, `app_settings_table`, and any reusable column lists so services stop importing ORM models.
     - `app/db/notes_sql.py`: focused write helpers (`insert_note`, `update_note_content`, `update_links`, `delete_notes`, `bulk_fetch_for_cache`) built on `Connection.execute` with compiled Core expressions; returns plain dicts/tuples.
     - `app/db/settings_sql.py`: read/write helpers for `AppSettings`, PBKDF2 metadata, maintenance toggles, etc. Uses `allow_reads` to fetch and explicit `update` / `insert` for writes.
     - Testing utilities extend `tests/unit/common.py` to use `engine.begin()` instead of ORM Session.
   - **Undo/redo capture design:**
     - Replace ORM event listeners with service-level snapshots. Each transactional service (e.g., `NoteService`) calls `transaction_manager.capture_before(note_ids)` to clone affected `NoteStore` nodes (content + linkage) before mutation, and `capture_after(note_ids)` right after helper calls.
     - `ApiTransaction` evolves into a lightweight dataclass storing lists of `NoteState` records (simple dicts) rather than ORM copies; `Command` operates purely on helper functions (`insert_note`, `update_note_links`, `delete_notes`) plus `NoteStore` mutations.
     - `TransactionManager` finalizes by diffing the pre/post snapshots (via `NoteStore` or captured dicts) instead of relying on SQLAlchemy’s identity map.

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
