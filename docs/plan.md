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
- Polling-based synchronization for multi-client updates
- Maintain existing URL-based state for bookmarking/sharing
- Use fractional indexing for positions (like Notion)
- Use integer indentation for hierarchy

### Technical Approach
- Use Fetch API for AJAX requests
- Implement a client-side state manager
- DOM updates via targeted element manipulation
- Keep server-side routes but modify responses
- Single-dimensional ordering with depth via indent

### Diff Format & Operations

#### Position Management
- Each note has:
  1. String-based position value (e.g., "a1", "b2", "a1.5")
  2. Integer indent level (0 = root, 1 = first level, etc.)
- New positions can always be generated between any two existing positions
- Natural ordering based on string comparison
- Hierarchy managed through indent level

#### Finding Child Notes
Initial Implementation:
- Binary search to find start of children (position > parent, indent = parent + 1)
- Scan until we hit a note with indent <= parent indent
- Works for all descendant levels (children, grandchildren, etc.)
- Example hierarchy:
  ```
  A (pos:a1, indent:0)
      B (pos:a2, indent:1)
          C (pos:a3, indent:2)
  D (pos:b1, indent:0)
      E (pos:b2, indent:1)
  ```

Future Optimization:
- Add database indexes for efficient tree operations
- Index on (position, indent) for range queries
- Enables fast subtree selection
- Will be implemented when performance requires it

#### Core Operations
1. Moving Notes
   - Updates parent note's:
     - position
     - indent level
   - Must cascade to all child notes:
     - Update their positions to maintain ordering
     - Adjust their indent levels relative to parent
   - Server handles all cascading updates
   - Returns changes for parent and all affected children

2. Deleting Notes
   - Simple operation with noteId
   - No need to update adjacent notes
   - Position space can be reused

3. Adding Notes
   - Server generates position between siblings
   - Sets appropriate indent level
   - No impact on existing notes

4. Content Updates
   - Fire-and-forget from client
   - No position/indent changes needed
   - Client handles optimistic updates

#### Proposed Diff Format
Example JSON structure:

{
  "changes": {
    "added": [
      {
        "id": "note_id",
        "version": 1,
        "hash": "sha256_of_note_data",
        "position": "a1.5",
        "indent": 2,
        "content": "note content"
      }
    ],
    "updated": [
      {
        "id": "note_id",
        "version": 5,
        "hash": "new_sha256_hash",
        "position": "b3",            // only if moved
        "indent": 1,                // only if changed
        "content": "updated content" // only if changed
      }
    ],
    "deleted": ["note_id1", "note_id2"]
  }
}

## Position Management
The system uses the `fractional-indexing` library to generate lexicographically ordered position strings. This allows inserting new items between any two existing positions without having to rebalance or update other positions.

The library generates short position strings (typically 2-3 characters) that maintain their order:
- First position is "a0"
- Positions after: "a1", "a2", etc.
- Positions before: "Zz", "Zy", "Zx", etc. (using ASCII ordering where uppercase comes before lowercase)
- Can extend to longer strings (e.g., "YzN") when more granularity is needed

This scheme allows for infinite positions in both directions while keeping strings compact.

### Versioning Strategy

#### Note Versioning
- Each note has:
  1. Integer version (increments with each change)
  2. Content hash (SHA-256 of entire note)
- Hash includes ALL note data:
  - content
  - position
  - indent
  - version
  - id
- Used for:
  - Detecting conflicts
  - Verifying note integrity
  - Identifying duplicates
  - Optimistic locking

### Synchronization Strategy

#### Polling Mechanism
- Every poll is fundamentally a search operation
- Client must always include current search string
- Regular polls to /api/changes?since=timestamp&search=query
- Configurable poll interval (default: 5s)
- Exponential backoff on empty responses

#### State Management
- Initial load gets full state matching search criteria
- Subsequent polls include:
  1. Current search string (required)
  2. Last sync timestamp
  3. Currently visible note IDs (for optimization)
- Server returns:
  1. Updates to currently visible notes
  2. New notes that now match search string
  3. Notes that became visible due to content changes

#### Example Poll Request
{
  "last_sync": "2024-01-20T15:30:00Z",
  "search_criteria": {
    "query": "work",  // Required - current search string
    "filters": ["active", "!archived"]
  },
  "visible_notes": ["note_id1", "note_id2", ...]
}

#### Example Poll Response
{
  "changes": {
    "added": [
      {
        "id": "new_note_id",
        "version": 1,
        "hash": "sha256_of_note_data",
        "position": "a1.5",
        "indent": 2,
        "content": "new #work note"
      }
    ],
    "updated": [
      {
        "id": "note_id",
        "version": 5,
        "hash": "new_sha256_hash",
        "position": "b3",
        "indent": 1,
        "content": "updated to include #work"
      }
    ],
    "deleted": ["note_id1"]
  },
  "timestamp": "2024-01-20T15:30:05Z"
}

## Current Status

### Completed
- Basic note structure and relationships
- Position string generation logic
  - Successfully implemented using fractional indexing
  - Handles infinite positions in both directions
  - Maintains short, efficient position strings
  - All tests passing including edge cases

### Next Steps
1. Integrate position strings into data model
   - Add position string field
   - Add indent level field
   - Update schema to support both old and new fields
   - Implement parallel system for validation
2. Implement the note storage system
   - Design the database schema
   - Create SQLAlchemy models
   - Implement CRUD operations
3. Build the REST API endpoints
   - Note creation/deletion
   - Note movement and reordering
   - Parent/child relationship management

## Implementation Steps

### 1. Position Management System
- [x] Implement fractional indexing
  - [x] Position string generation
  - [x] Position comparison/sorting
  - [x] Generate position between two others
  - [x] Handle edge cases (first/last positions)

- [ ] Add new fields without removing old
  - [ ] Add position string field
  - [ ] Add indent level field
  - [ ] Keep prev/next/parent working
  - [ ] Update schema to support both

- [ ] Add indent level support
  - [ ] Calculate indent from parent relationships
  - [ ] Update display to use indentation
  - [ ] Validate indent constraints

- [ ] Parallel implementation testing
  - [ ] Update operations maintain both systems
  - [ ] Compare tree structure between approaches
  - [ ] Verify ordering matches
  - [ ] Test edge cases in both systems
  - [ ] Add logging/monitoring for discrepancies

- [ ] Gradual migration
  - [ ] Feature flag for new system
  - [ ] Log any differences between systems
  - [ ] Roll back capability if issues found
  - [ ] Remove old fields only after thorough testing

### 2. Versioning System
- [ ] Add version/hash to notes
  - [ ] Add version and hash fields
  - [ ] Implement hash calculation
  - [ ] Version increment logic
- [ ] Implement optimistic locking
  - [ ] Version checking on updates
  - [ ] Conflict detection
  - [ ] Merge strategy
- [ ] Add version management API
  - [ ] Version validation
  - [ ] Hash verification
  - [ ] Conflict resolution endpoints

### 3. Differential Updates
- [ ] Implement diff format
  - [ ] Change detection
  - [ ] Diff generation
  - [ ] Diff application
- [ ] Add polling mechanism
  - [ ] Poll endpoint with search
  - [ ] Change filtering
  - [ ] Response formatting
- [ ] Client-side state management
  - [ ] State tracking
  - [ ] Update application
  - [ ] Error handling

### 4. Testing & Integration
- [ ] Unit tests for each system
  - [ ] Position management tests
  - [ ] Version/hash tests
  - [ ] Diff generation/application tests
- [ ] Integration tests
  - [ ] Full update cycle tests
  - [ ] Concurrent modification tests
  - [ ] Error recovery tests
- [ ] Performance testing
  - [ ] Position generation performance
  - [ ] Poll response times
  - [ ] State update speed

### 5. Documentation & Cleanup
- [ ] API documentation
  - [ ] Position management
  - [ ] Versioning
  - [ ] Diff format
- [ ] Implementation notes
  - [ ] Position generation algorithm
  - [ ] Hash calculation
  - [ ] State management
- [ ] Remove old code
  - [ ] Remove linked list code
  - [ ] Clean up old routes
  - [ ] Update schemas 

#### Transition Data Structure
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  // Old system fields
  "prev_id": "550e8400-e29b-41d4-a716-446655440000",
  "next_id": "987fcdeb-51d3-12d3-a456-426614174000",
  "parent_id": "abc123de-f456-789g-hij0-klmnopqrstuv",
  // New system fields
  "fractional_position": "a1.5",
  "indent": 2,
  // Common fields
  "content": "note content",
  "version": 1,
  "hash": "sha256_of_note_data"
}
```

#### Validation Process
1. For any note:
   - Calculate expected position from prev/next relationships
   - Calculate expected indent from parent relationship
   - Compare with fractional_position and indent
   - Log any discrepancies

2. For the entire tree:
   - Walk the linked list (prev/next)
   - Walk the sorted positions
   - Verify both produce same ordering
   - Verify all parent/child relationships match indent levels

3. For each operation:
   - Update both systems
   - Verify they remain in sync
   - Alert on any differences 

#### Backwards Compatibility Strategy

##### Conversion Layer
```typescript
interface LegacyNote {
  id: string;
  prev_id: string | null;
  next_id: string | null;
  parent_id: string | null;
  content: string;
}

interface ModernNote {
  id: string;
  position: string;
  indent: number;
  content: string;
  version: number;
  hash: string;
}

// Conversion functions maintain old interface
function toLegacyFormat(note: ModernNote, allNotes: ModernNote[]): LegacyNote {
  return {
    id: note.id,
    prev_id: findPrevId(note.position, note.indent, allNotes),
    next_id: findNextId(note.position, note.indent, allNotes),
    parent_id: findParentId(note.position, note.indent, allNotes),
    content: note.content
  };
}

// All old tests can use this wrapper
function getNoteById(id: string): LegacyNote {
  const modernNote = db.getNoteById(id);
  const allNotes = db.getAllNotes();
  return toLegacyFormat(modernNote, allNotes);
}
```

##### Testing Strategy
1. Keep all existing tests unchanged
2. Add conversion layer in test environment
3. Add new tests for modern features
4. Validate both representations match
5. Eventually deprecate legacy tests

##### Benefits
- No need to rewrite existing tests
- Gradual migration path
- Double validation of behavior
- Safe rollback option
- Clear deprecation path 