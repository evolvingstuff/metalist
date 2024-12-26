# Frontend Refactoring Plan

## 1. Project Setup [✓]
- [✓] Create module directory structure
- [✓] Set up build process if needed
- [✓] Configure module imports/exports

## 2. Core Modules Implementation

### 2.1 Configuration (config.js) [✓]
- [✓] Define configuration constants
- [✓] Add debug flags
- [✓] Add API endpoints
- [✓] Add CSS classes

### 2.2 API Client (api-client.js) [✓]
- [✓] Implement API wrapper
- [✓] Add error handling
- [✓] Add debug logging
- [✓] Handle different response types

### 2.3 DOM Utilities (dom-utils.js) [✓]
- [✓] Extract DOM manipulation methods
- [✓] Add element finders/selectors
- [✓] Implement cursor position handling
- [✓] Add content management utilities

### 2.4 Note State Management (note-state.js) [✓]
- [✓] Implement NoteState module
- [✓] Extract state variables from global scope
- [✓] Add auto-save functionality
- [✓] Handle editing state transitions

### 2.5 Event Handlers (event-handlers.js) [✓]
- [✓] Implement event delegation system
- [✓] Extract click handlers
- [✓] Extract keyboard handlers
- [✓] Extract drag-and-drop handlers
- [✓] Implement event coordination

## 3. Main.js Refactoring [ ]
- [ ] Remove global variables
- [ ] Initialize modules
- [ ] Set up event listeners
- [ ] Clean up old code
- [ ] Add error boundaries

## 4. Testing [ ]
- [ ] Set up Jest testing environment
- [ ] Write tests for DOM utilities
- [ ] Write tests for state management
- [ ] Write tests for API client
- [ ] Add integration tests

## 5. Documentation [ ]
- [ ] Add JSDoc comments
- [ ] Create module documentation
- [ ] Add usage examples
- [ ] Document testing procedures

## 6. Performance Optimization [ ]
- [ ] Add performance monitoring
- [ ] Optimize DOM operations
- [ ] Implement request batching
- [ ] Add caching where appropriate

## Future Improvements

### API Refinements

Split the generic `/move` endpoint into more specific use cases:
- `/move/sibling` - Moving between siblings at same level
- `/move/indent` - Moving a note to become a child of another note
- `/move/outdent` - Moving a note out to parent level
- `/move/reorder` - Reordering notes at the same level

Benefits:
- More semantic and self-documenting API
- Simplified validation logic
- Easier debugging
- Cleaner frontend implementation

## Next Steps:
1. Refactor main.js to use our new modules
2. Set up testing infrastructure
3. Add comprehensive documentation
4. Implement performance optimizations 

## Planned Improvements

- [ ] Refactor main.js into smaller modules
- [ ] Add proper error handling for API calls
- [ ] Add loading states for operations
- [ ] Apply ensureNotesSaved pattern to all note operations
- [x] Auto-focus new notes after creation
- [x] Maintain cursor position after note movement
- [x] Fix sibling note movement while preserving parent-child relationships

### API Refinements

Split the generic `/move` endpoint into more specific use cases:
- `/move/sibling` - Moving between siblings at same level
- `/move/indent` - Moving a note to become a child of another note
- `/move/outdent` - Moving a note out to parent level
- `/move/reorder` - Reordering notes at the same level

Benefits:
- More semantic and self-documenting API
- Simplified validation logic
- Easier debugging
- Cleaner frontend implementation

## Fixed Bugs

- [x] Root level notes had "None" as parent_id in HTML instead of empty string
- [x] Drag and drop movement of notes wasn't preserving parent-child relationships
- [x] Content was lost when creating new notes via Cmd+Enter due to incorrect edit state checking 