# Dynamic Notes Container Update Plan

## Current Setup
- Notes rendered via notes_list.html template
- Most operations trigger full page reload via window.location.reload()
- Content updates are "fire and forget" (no reload)
- Clean component separation already exists

## Proposed Solution
### Server Changes
- Add dedicated fragment endpoint for HTML updates:
  ```python
  @router.get("/fragment")
  def get_notes_fragment(db: Session = Depends(get_db)):
      notes = LinkedListManager.get_all_notes(db)
      html = render_template('notes_list.html', notes=notes)
      return {"data": {"html": html}}
  ```

### Client Changes
- Update api-client.js to use fragment endpoint:
  ```javascript
  async _apiCall(url, options = {}, needsUpdate = true) {
    const response = await fetch(url, options);
    const data = await response.json();

    if (needsUpdate) {
      // Get HTML fragment
      const fragmentResponse = await fetch('/api/notes/fragment');
      const fragmentData = await fragmentResponse.json();
      
      // Update DOM
      document.getElementById('notes-container').innerHTML = fragmentData.data.html;
      
      // Restore state
      this._restoreState();
    }
    
    return data;
  }
  ```

## Implementation Steps

### 1. Server-Side Changes
[ ] Add `/api/notes/fragment` endpoint:
    - [ ] Import required dependencies (mako, os)
    - [ ] Set up template lookup
    - [ ] Get notes from DB
    - [ ] Render and return HTML

### 2. Client-Side Changes
[ ] Update `api-client.js`:
    - [ ] Restore NoteState import
    - [ ] Change reloadOnSuccess back to needsUpdate
    - [ ] Add fragment fetch logic
    - [ ] Add state restoration logic
    - [ ] Test all API methods

### 3. Testing
[ ] Test all note operations:
    - [ ] Create (top-level, sibling, child)
    - [ ] Move (up, down, drag & drop)
    - [ ] Delete
    - [ ] Undo/Redo
    - [ ] Content updates (should not trigger reload)

### 4. Verification
[ ] Verify state management:
    - [ ] Editing state preserved
    - [ ] Cursor position maintained
    - [ ] New note focus works
    - [ ] No unwanted page reloads

## Benefits
- No full page reloads
- Better Cypress test compatibility
- Maintains existing "fire and forget" behavior
- Keeps server-side rendering
- Consistent JSON API responses

## Future Options
- Add WebSocket/SSE later if needed
- Could add optimistic updates
- Could implement proper diffs
