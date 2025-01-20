# Development Plan

## Current Focus: Note Reordering
Moving notes up/down within their sibling group using keyboard shortcuts.

### Implementation Steps
- [ ] Add keyboard shortcut handling in editing state
  - [ ] Detect Cmd-UpArrow
  - [ ] Detect Cmd-DownArrow
  - [ ] Handle edge cases (first/last sibling)
- [ ] Add API endpoint for reordering
  - [ ] Move note before sibling
  - [ ] Move note after sibling
- [ ] Add effect for reordering
  - [ ] Create MoveNoteEffect
  - [ ] Queue effect on shortcut
  - [ ] Let fragment refresh handle re-render

### Future Features
- [ ] Drag and Drop from Add Button
  - [ ] Add sibling (above/below note)
  - [ ] Add child (middle of note)
- [ ] Drag Note to Delete
  - [ ] Drag note to trash
  - [ ] Visual feedback during drag

## Architectural Principles

### Single Source of Truth
- Backend owns all note data and structure
- Frontend is just a view into that data
- Changes must go through API
- Fragment refresh handles re-rendering

### DOM Manipulation Rules
✅ Allowed:
- UI interactions (focus, blur)
- contenteditable state
- Cursor position
- Search input focus

❌ Not Allowed:
- Note structure changes
- Direct note reordering
- Content updates without API

### State Machine Patterns
1. Event Flow:
   ```
   DOM Event -> Raw Event -> State Handler -> Effect -> API -> Fragment Refresh
   ```

2. State Changes:
   ```
   Current State -> Exit Handler -> Run Effects -> API Call -> Fragment Refresh -> Enter Handler
   ```