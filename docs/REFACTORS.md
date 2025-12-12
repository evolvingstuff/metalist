# Refactors

## Note ordering: duplicate sources of truth

### Symptom ("top note gets eaten")
- Repro: create a new note at the top → type → `Esc` → collapse/expand any other note.
- Result: the newly-created top note jumps to the bottom, and the UI appears to freeze due to a massive reorder (tens of thousands of VDOM ops).
- Restarting the server makes the issue disappear.

### Root cause
The server keeps *two* representations of note ordering:

1. `NoteStore._links/_heads/_tails` (the live, incremental linked-list used by `NoteStore.get_children()`)
2. `NoteRecord.prev_id/next_id` stored inside `NoteStore._note_map` (used by some rebuild/reorder paths)

Some mutation paths updated `_links` but did **not** update neighboring `NoteRecord.prev_id/next_id` pointers.
Later, a code path that rebuilt indexes from the record pointers would “rediscover” an ordering based on stale pointers and reorder the list.

### Fix (current): keep pointers in sync + fail-fast invariants
Implemented “Option B”: whenever `_links` is mutated, also update the affected `NoteRecord` pointers for:
- the inserted/removed node
- its immediate neighbors (prev/next)

Then assert local invariants immediately:
- record parent matches link parent
- record prev/next matches `_links` prev/next
- prev.next and next.prev symmetry
- head/tail consistency for the touched parent list

Files:
- `app/services/note_store.py`
  - `_insert_link()` updates neighbor `NoteRecord` pointers and asserts consistency
  - `_remove_link()` updates neighbor `NoteRecord` pointers and asserts consistency
  - `_assert_links_consistent_locked()` is the fail-fast invariant check

### Future plan (preferred): single source of truth (Option A)
Option B is still duplicated state. The longer-term direction should be:

- Make `_links/_heads/_tails` the *only* source of truth for ordering.
- Avoid rebuilding ordering from `NoteRecord.prev_id/next_id` (or stop storing prev/next in `NoteRecord` at all).
- If `prev_id/next_id` are needed for external/DB serialization, derive them from `_links` on demand.

Why A is better:
- No drift: you can’t update one representation and forget the other.
- Fewer mutation bugs: ordering correctness becomes simpler to reason about.

Why A is not done yet:
- Requires touching multiple call sites that assume record pointers are authoritative.
- Needs careful perf work (deriving pointers cheaply) and incremental migration.

