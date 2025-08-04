# Simple Search Implementation Plan

## Overview
Implement a basic search functionality that filters notes based on text content. The search will use AND logic (all words must be present) and will include a note if either the note itself or any of its descendants contain all search terms.

## Backend Implementation

### 1. HTML Stripping Utility
- Create `app/utils/text_utils.py`
- Function: `strip_html(html_content: str) -> str`
- Remove all HTML tags and return plain text
- Handle common HTML entities (&amp;, &lt;, etc.)

### 2. Search Parameter in API
- Modify `get_notes_fragment` in `app/api/notes.py`
- Add optional `search: Optional[str] = None` query parameter
- Pass search parameter to query service

### 3. Search Logic in Note Query Service
- Modify `get_notes_fragment` in `app/services/query_service.py`
- Pass search parameter to note tree builder
- Implement filtering before rendering

### 4. Note Tree Filtering
- Modify `build_note_tree` in `app/render/note_renderer.py`
- Add search parameter
- Implement recursive search logic:
  ```python
  def note_matches_search(note, search_terms, all_notes):
      # Check if note content contains all search terms
      # OR if any descendant contains all search terms
      # Return True if match, False otherwise
  ```

## Frontend Implementation

### 5. Search UI Element
- Search input already exists in `app/templates/index.html` with id="search-input"
- Located in controls div at top of page

### 6. Search State Management
- Add to `app/static/js/modules/mode-manager/mode-context.js`:
  - `_searchQuery: ''`
  - `setSearchQuery(query)` method
  - `get searchQuery()` getter

### 7. Search Input Handler
- Create `app/static/js/modules/mode-manager/events/search-events.js`
- Add SEARCH_DEBOUNCE_MS to `app/static/js/modules/config.js`
- Implement debounced input handler using configured delay
- Update ModeContext on search change

### 8. Fragment Reload on Search
- Modify `actionRefreshView` in `app/static/js/modules/mode-manager/actions/ui-actions.js`
- Include search query when fetching fragment
- Update `NotesAPI.getFragment` to accept search parameter

## Implementation Order

1. **Backend first** (easier to test):
   - HTML stripping utility
   - API parameter addition
   - Search filtering logic
   - Test with manual API calls

2. **Frontend integration**:
   - Add search input UI
   - Wire up state management
   - Connect input to API calls
   - Test end-to-end

## Search Algorithm Details

### Word Splitting
- Split search query by spaces
- Trim whitespace from each word
- Ignore empty strings

### Matching Logic
```
For each note in tree:
  1. Strip HTML from note content
  2. Convert to lowercase
  3. Check if ALL search words exist in content
  4. If not, recursively check all descendants
  5. Include note if it OR any descendant matches
```

### Edge Cases
- Empty search query → show all notes
- No matches → show empty result
- Special characters in search → treat as literal text

## Testing Plan

1. **Unit Tests**:
   - HTML stripping with various HTML inputs
   - Search matching logic with different word combinations
   - Tree filtering with nested structures

2. **Integration Tests**:
   - API endpoint with search parameter
   - Frontend search input and debouncing
   - Full search flow

3. **Manual Testing Scenarios**:
   - Single word search
   - Multi-word search (AND logic)
   - Search with HTML content
   - Nested note matching
   - Empty search results
   - Clear search to show all

## Future Enhancements (NOT in this PR)
- OR logic option
- Regex support
- Search highlighting
- Search history
- Performance optimization (indexing)
- Fuzzy matching