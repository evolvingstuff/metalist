# Move Database Operations to Effects

## Overview
Move all database-affecting operations into Effect classes to centralize side effects and make state transitions pure.

## Tasks

### 1. Create New Effects
- [x] Create `UpdateNoteEffect` for auto-saving note content (fire & forget)
- [x] Create `SaveNoteEffect` for explicit note saves (with confirmation)
- [x] Create `CreateChildEffect` for creating child notes
- [x] Create `CreateSiblingEffect` for creating sibling notes
- [x] Create `DeleteNoteEffect` for deleting notes
- [ ] Create `MoveNoteEffect` for moving notes

### 2. Update State Transitions
- [x] Move note update logic from `editing.exit()` to use `UpdateNoteEffect`
- [x] Move explicit save logic to use `SaveNoteEffect`
- [x] Move child creation from KEY_DOWN handler to use `CreateChildEffect`
- [x] Move sibling creation from KEY_DOWN handler to use `CreateSiblingEffect`
- [ ] Update any delete operations to use `DeleteNoteEffect`
- [ ] Update any move operations to use `MoveNoteEffect`

### 3. Testing
- [ ] Test `UpdateNoteEffect`
- [ ] Test `SaveNoteEffect` 
- [ ] Test `CreateChildEffect`
- [ ] Test `CreateSiblingEffect`
- [ ] Test `DeleteNoteEffect`
- [ ] Test `MoveNoteEffect`
- [ ] Test state transitions use effects correctly

### 4. Cleanup
- [ ] Remove direct API calls from state transitions
- [ ] Update documentation to reflect new effect pattern
- [ ] Add error handling in effects
- [ ] Review and clean up any remaining direct database operations

## Benefits
1. All database operations centralized in effects.js
2. State transitions become pure 
3. Effects handle all state context updates
4. Easier to test - can mock effects
5. Clearer what operations affect the database