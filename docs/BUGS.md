# Known Bugs

----

## Undo referential integrity regression (adapter removal)

When migrating usecases to call `app/services/note_store.py` directly (removing
the `app/services/store.py` adapter), certain undo sequences (delete or move
down) left the in-memory links in an invalid state, causing the UI to enter a
loading/unresponsive state. Stashing those changes (restoring the adapter)
returns stability.

Status: adapter kept; revisit later with link invariants and stepwise migration.

Suggested approach:
- Add `note_store.debug_validate_links()` checks after each apply_* in undo flows
  (move, delete, restore) to pinpoint inconsistencies early.
- Migrate one usecase at a time (e.g., update_content → delete → move) and test
  undo/redo sequences before removing the adapter entirely.

----

## Errors when moving notes

When moving notes up or down in the outline, it works fine 
for outermost layer (notes without parents),
but fails when moving child notes within parents.

1. Click into note A
2. Press shift-cmd-enter to create child A.A
3. Press cmd-enter to create sibling A.B
4. with A.B selected, press cmd-uparrow. This will cause server errors

----
