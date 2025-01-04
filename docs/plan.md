# Dynamic Notes Container Update Plan

## Current Setup
- Notes rendered via notes_list.html template
- Most operations trigger full page reload
- Content updates are "fire and forget" (no reload)
- Clean component separation already exists

## Proposed Solution
### Server Changes
- Modify API responses to include HTML when needed:
  ```python
  return {
    "success": True,
    "data": {
      "id": note.id,  # or other operation-specific data
      "html": render_template('notes_list.html', notes=notes)  # only when needsUpdate=True
    }
  }
  ```

### Client Changes
- Update api-client.js:
  ```javascript
  async _apiCall(url, options = {}, needsUpdate = true) {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    });
    
    if (!response.ok) {
      throw new Error(`API call failed: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();

    // For operations that need the updated notes list
    if (needsUpdate && data.data.html) {
      document.getElementById('notes-container').innerHTML = data.data.html;
      // Reattach any needed event listeners
      return data;
    }
    
    return data;
  }
  ```

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
