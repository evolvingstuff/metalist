# Differential Updates Implementation Plan

## Design Decisions

### Why Differential Updates?
- Eliminates full page reloads, improving user experience
- Better aligns with modern web practices
- Makes testing easier (especially with Cypress)
- Reduces server load by sending only changed data

### Key Architecture Changes
- Server will return JSON responses instead of triggering page reloads
- Client will handle state management and DOM updates
- WebSocket connection for real-time updates
- Maintain existing URL-based state for bookmarking/sharing

### Technical Approach
- Use Fetch API for AJAX requests
- Implement a client-side state manager
- DOM updates via targeted element manipulation
- Keep server-side routes but modify responses

### Diff Format & Operations

#### Core Operations
1. Moving Notes
   - Maintains linked-list structure for scalability
   - Client specifies: parent_id, prev_id, next_id
   - Server calculates all cascading updates
   - Returns diff of all affected nodes

2. Deleting Notes
   - Client sends single noteId
   - Server handles prev/next pointer updates
   - Returns diff including changes to adjacent nodes

3. Adding Notes
   - Similar to move operation
   - Position specified via parent/prev/next
   - Server handles all linking
   - Returns diff of all affected nodes

4. Content Updates
   - Fire-and-forget from client
   - No server response needed
   - Client handles optimistic updates

#### Proposed Diff Format
Example JSON structure:

```
{
  "transaction_id": "uuid",
  "changes": {
    "added": [
      {
        "id": "note_id",
        "parent_id": "parent_id",
        "prev_id": "prev_note_id",
        "next_id": "next_note_id",
        "content": "note content"
      }
    ],
    "updated": [
      {
        "id": "note_id",
        "prev_id": "new_prev_id",    // only included if changed
        "next_id": "new_next_id",    // only included if changed
        "parent_id": "new_parent",   // only included if changed
        "content": "updated content" // only included if changed
      }
    ],
    "deleted": ["note_id1", "note_id2"]
  }
}
```

This format:
- Groups changes by type (add/update/delete)
- Only includes changed fields
- Handles multiple node updates in single diff
- Includes transaction ID for tracking/debugging

## Implementation Steps

### 1. Server-Side Changes
- [ ] Modify route handlers to return JSON instead of redirects
  - [ ] `/api/notes/new` returns note data
  - [ ] `/api/notes/<id>` returns updated note
  - [ ] `/api/notes/<id>/delete` returns success status
- [ ] Add response status codes and error handling
  - [ ] 200 for successful operations
  - [ ] 404 for missing notes
  - [ ] 400 for invalid requests
- [ ] Implement WebSocket endpoint for real-time updates
  - [ ] Set up WebSocket server
  - [ ] Define message protocol
  - [ ] Handle client connections/disconnections

### 2. Client-Side State Management
- [ ] Create state management module
  - [ ] Define state structure
  - [ ] Implement state update methods
  - [ ] Add state change listeners
- [ ] Add local caching
  - [ ] Cache note data
  - [ ] Handle cache invalidation
  - [ ] Sync with server state

### 3. DOM Updates
- [ ] Create DOM update manager
  - [ ] Methods for creating note elements
  - [ ] Methods for updating note content
  - [ ] Methods for removing notes
- [ ] Implement differential rendering
  - [ ] Compare old/new state
  - [ ] Update only changed elements
  - [ ] Handle animations/transitions

### 4. API Integration
- [ ] Replace form submissions with Fetch API calls
  - [ ] Note creation
  - [ ] Note updates
  - [ ] Note deletion
- [ ] Add request error handling
  - [ ] Network errors
  - [ ] Server errors
  - [ ] Invalid responses
- [ ] Implement optimistic updates
  - [ ] Update UI immediately
  - [ ] Rollback on failure

### 5. Real-Time Updates
- [ ] Implement WebSocket client
  - [ ] Connection management
  - [ ] Message handling
  - [ ] Reconnection logic
- [ ] Handle concurrent edits
  - [ ] Conflict detection
  - [ ] Merge strategies
  - [ ] User notifications

### 6. Testing
- [ ] Update existing tests for new architecture
  - [ ] Modify Cypress tests
  - [ ] Add WebSocket tests
  - [ ] Test state management
- [ ] Add new test coverage
  - [ ] Network error handling
  - [ ] State synchronization
  - [ ] Real-time update scenarios

### 7. Documentation & Cleanup
- [ ] Update API documentation
  - [ ] New endpoints
  - [ ] Response formats
  - [ ] WebSocket protocol
- [ ] Add client architecture docs
  - [ ] State management
  - [ ] Update flow
  - [ ] Error handling
- [ ] Clean up legacy code
  - [ ] Remove page reload logic
  - [ ] Update dependencies
  - [ ] Optimize bundles 