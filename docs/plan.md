# Note Rendering System Implementation

## Overview
Implement a system for rendering notes differently when viewing vs editing, with proper state management and cursor handling.

## Tasks

### Backend Changes
- [ ] Add placeholder render functions in notes.py:
  - [ ] `is_renderable(note)` - Always returns False for now
  - [ ] `maybe_render_content(note)` - Returns raw content for now
- [ ] Add `editing_note_id` parameter to `/fragment` endpoint
- [ ] Update `build_tree` to use render functions and set flags:
  - [ ] Pass `editing_note_id` through
  - [ ] Add `isRendered` flag based on `is_renderable`
  - [ ] Use `maybe_render_content` for non-edited notes

### Frontend State Machine Changes
- [ ] Remove fragment loading from API client:
  - [ ] Remove `reloadOnSuccess` parameter from `_apiCall`
  - [ ] Remove fragment fetching logic from `_apiCall`
  - [ ] Update all API call sites to remove `reloadOnSuccess`
- [ ] Add fragment loading to state machine:
  - [ ] Create command function to load fragment with editing_note_id
  - [ ] Add check for `rendered-content` class (throw for now)
  - [ ] Update DOM with new fragment
- [ ] Update state transitions:
  - [ ] Add fragment command to any transition involving editing state:
    - [ ] When transitioning TO editing: pass next note's ID
      - [ ] idle -> editing
      - [ ] editing -> editing
      - [ ] searching -> editing
    - [ ] When transitioning FROM editing: pass null
      - [ ] editing -> idle
      - [ ] editing -> searching
  - [ ] Remove any other fragment loading

### Template Changes
- [ ] Update notes_list.html:
  - [ ] Add `editing` class based on `isEditing` flag
  - [ ] Add `rendered-content` class based on `isRendered` flag

### Testing
- [ ] Verify existing tests pass with placeholder render functions
- [ ] Add tests for fragment endpoint with `editing_note_id`
- [ ] Add tests for state transitions with rendered content
- [ ] Test error handling for rendered content (not implemented yet)

### Documentation
- [ ] Document render function interfaces
- [ ] Document fragment endpoint parameters
- [ ] Document state transition flow with fragments
- [ ] Document rendered content handling (future implementation)

### Future Work (Not Implemented Yet)
- [ ] Implement actual content rendering
- [ ] Add render type detection
- [ ] Handle cursor positioning for rendered content
- [ ] Add schema support for note render types
- [ ] Add fragment loading for other state needs:
  - [ ] Search results display
  - [ ] Filter/sort changes
  - [ ] Any other dynamic content updates
- [ ] Refine fragment loading patterns:
  - [ ] Consider breaking down by event type
  - [ ] Add more granular control over when fragments load
  - [ ] Keep simple "editing involved" pattern for now