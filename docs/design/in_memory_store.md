# In-Memory Note Store Design

## Goals
- Load the entire note hierarchy into memory once at startup.
- Eliminate runtime SQL reads during normal operation.
- Provide fast lookups for rendering, search, and hierarchy manipulation.
- Preserve undo/redo behavior (temporarily permit DB reads during replay).
- Support forthcoming diff-based sync by tracking per-note hashes and render variants.

## Architecture Overview
```
Startup
└─ load notes from DB
   ├─ populate content cache (existing)
   ├─ build NoteStore (new):
   │    - note_map[id] = NoteRecord (content, metadata, hashed variants)
   │    - children[parent_id] = ordered list of child ids
   │    - root_order = ordered list of root ids
   │    - hash_tree = hierarchical hashes (collapsed/expanded/edit)
   └─ flip ReadGuard.enable()
```

### Core Components
- `NoteStore`: central in-memory data structure holding notes, orderings, and pre-rendered variants.
- `ReadGuard`: global flag enforced inside `SafeSession.execute`; raises on SELECT once enabled.
- `LinkedListManager` / `ListTraversal`: refactored to operate on `NoteStore` instead of issuing queries.
- `NoteRenderer`: produces three render variants (collapsed, expanded, edit) stored per note.

## Data Structures
```python
@dataclass
class NoteRenderVariants:
    collapsed_html: str
    expanded_html: str
    edit_html: str
    hash_collapsed: str
    hash_expanded: str
    hash_edit: str

@dataclass
class NoteRecord:
    id: str
    parent_id: Optional[str]
    prev_id: Optional[str]
    next_id: Optional[str]
    is_collapsed: bool
    content: str  # decrypted
    created_at: datetime
    updated_at: datetime
    variants: NoteRenderVariants
```

Supporting containers:
- `note_map: dict[str, NoteRecord]`
- `children: dict[Optional[str], list[str]]` (root uses `None` key)
- `hash_tree: dict[str, str]` (combined hash of note + subtree)

## Startup Flow
1. DB initialization runs as today (create tables, populate cache).
2. New `NoteStore.load_from_db(session)` performs a single read of `notes` table, constructs `NoteRecord`s, and computes variants/hashes via renderer.
3. `ReadGuard.enable()` prevents subsequent SQL reads unless explicitly disabled.

## Mutation Workflow
- Service layer (e.g., `NoteService`) updates `NoteStore` first:
  - Add/remove note IDs from `children`/`note_map`.
  - Update linked-list pointers in memory.
  - Recompute render variants + hashes.
- Persist change to DB via sqlite helpers (write-through).
- Existing cache listeners remain to keep `_search_cache` synced.

## Undo/Redo Exception
- `UndoRedoService` wraps replay operations in `ReadGuard.allow_reads("undo"/"redo")` context.
- During this window the sqlite helpers can fetch/compare DBNote states without raising.
- After replay, guard re-enables automatically.

## Guard Implementation
- Extend `SafeSession` with a class-level `reads_enabled` flag.
- Override `execute` or attach event listeners checking if the statement is a SELECT.
- Throw `RuntimeError("Post-startup DB read forbidden")` when the guard is active.
- Provide `@contextmanager allow_reads(reason)` to temporarily permit selects (undo/redo).

## Rendering / Sync Changes
- `NoteQueryService.render_notes_view` uses `NoteStore` to fetch ordered roots and their variants.
- Diff protocol can leverage `hash_tree` and per-note hashes to send only changed nodes + their triple renderings.
- expand/collapse toggles update `NoteStore` state immediately; client receives precomputed HTML.

## Integrity Checks
- `ListTraversal.validate_list` rewritten to traverse `NoteStore` child lists.
- Optional: offline validator to compare `NoteStore` state vs DB after commits for early debugging.

## Testing Strategy
- Unit tests for `NoteStore` covering load, add, delete, move, hash updates.
- Integration tests verifying runtime `SELECT` raises once guard enabled (except within `allow_reads`).
- Performance benchmarks comparing pre/post store load and render speed.

## Future Work Hooks
- Store can emit events when hashes change to power WebSocket push updates.
- Investigate migrating undo snapshots into `NoteStore` instead of ORM to remove read exception long-term.
