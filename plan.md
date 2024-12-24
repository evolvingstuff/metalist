# Drag-to-Create Note Implementation Plan

## Overview
Add functionality to drag directly from the "+" button to create and position a new note in one action.

## Frontend Changes
- [ ] Make "+" button draggable while preserving click behavior
  - [ ] Add drag handle or modify button to support drag events
  - [ ] Implement drag start/end event handlers
  - [ ] Visual feedback during drag (cursor change, ghost element)

- [ ] Modify drag logic
  - [ ] Add flag to identify if drag originated from "+" button
  - [ ] If drag is from "+", override normal drag behavior
  - [ ] Use same drop targets/visualization as normal note dragging

- [ ] Update drop handling
  - [ ] If drag source is "+", generate new note ID
  - [ ] Send combined create+move operation to backend
  - [ ] Handle failed operations (revert visual state)

## Backend Changes
- [ ] Create new endpoint for combined create+move operation
  ```python
  POST /api/notes/create-at-position
  {
    "parent_id": "optional-parent-id",
    "sibling_id": "target-sibling-id",
    "position": "BEFORE|AFTER"
  }  ```

- [ ] Implement combined operation handler
  - [ ] Create transaction to handle both operations atomically
  - [ ] Generate new note ID on server side
  - [ ] Call existing create_note and move_note methods
  - [ ] Return new note ID and final position to frontend

## Testing
- [ ] Unit tests
  - [ ] Test combined create+move operation
  - [ ] Test transaction rollback on failure
  - [ ] Test invalid target scenarios

- [ ] Integration tests
  - [ ] Test drag-to-create workflow
  - [ ] Verify note positioning
  - [ ] Verify list integrity after operation

- [ ] UI tests
  - [ ] Test drag visualization
  - [ ] Test invalid drop targets
  - [ ] Test canceling drag operation

## Documentation
- [ ] Update API documentation
- [ ] Update user documentation
- [ ] Add examples of new drag-to-create functionality

## Future Considerations
- Consider adding visual indicator on "+" button to show it's draggable
- Consider adding keyboard shortcuts for this operation
- Consider adding undo/redo support for this combined operation 