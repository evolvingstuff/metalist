# State Handling in MetaList3

## ModeManager Architecture

The ModeManager is a modular state management system designed to replace the complex state machine previously used in MetaList3. Instead of exclusive states, it uses boolean flags (modes) that can be active simultaneously.

### Key Components

1. **ModeContext**: Central state store with boolean flags and context data
2. **Actions**: Centralized operations that affect state, make server calls, and trigger UI updates
3. **Event Handlers**: Map DOM events to appropriate actions
4. **Logger**: Categorized logging for debugging and monitoring

## Core Principles

### Separation of Concerns

- **Event Handlers** detect user interaction but DO NOT modify state directly
- **Actions** encapsulate complex operations including state changes, server calls, and UI updates
- **ModeContext** manages the actual state and validates invariants

This separation creates a flow that is more complex than a simple linear progression:

```
User Interaction → Event Handler → Action 
                                    ↓
                           ┌────────┼────────┐
                           ↓        ↓        ↓
                     State Change  API Call  UI Update
                           ↓        ↓
                           └───→ Response Handler
                                    ↓
                           ┌────────┼────────┐
                           ↓        ↓        ↓
                     State Change  API Call  UI Update
```

### Event-Action-State Pattern

1. **Events**: 
   - Handle raw DOM events (clicks, keypress, input)
   - Determine what action to take based on context
   - Perform basic filtering to avoid unnecessary actions
   - Can chain multiple actions together for complex interactions
   - NEVER modify state directly

2. **Actions**:
   - Encapsulate complex operations that may include:
     - State changes (via ModeContext)
     - API calls to the server
     - Handling API responses
     - Triggering UI updates
   - Validate inputs before proceeding
   - Maintain state consistency
   - Throw errors for invalid operations
   - Can be composed together for more complex operations

3. **State (ModeContext)**:
   - Store the application state
   - Provide getters and setters
   - Validate state invariants
   - Notify listeners of changes

### Validation Strategy

The system follows a "fail-fast" approach to error handling at multiple levels:

1. **Input Validation**: Actions validate their inputs before proceeding
2. **State Invariants**: The ModeContext enforces state consistency rules
3. **Redundancy Checks**: State setters fail on redundant state changes
4. **Error Propagation**: Errors are thrown and logged immediately when detected

Key invariants and validation rules include:
- If editing mode is active, a currentNoteId must be set
- If editing mode is not active, no currentNoteId should be set
- Setting a state flag to its current value is considered a programming error

#### Redundancy Checks vs. NOOP Pattern

The ModeManager implements two distinct approaches to handle potentially redundant operations:

1. **Redundancy Checks (in ModeContext)**: 
   ```javascript
   // Inside setEditing() method
   if (this._editing === value) {
     throw new Error(`Redundant state change: editing is already ${value}`);
   }
   ```
   These catch programming errors where code accidentally tries to set state to its current value.

2. **NOOP Pattern (in event handlers)**:
   ```javascript
   // In handleClick()
   if (ModeContext.isEditing && ModeContext.currentNoteId === noteId) {
     Logger.logNoop('Click in already selected note - no action needed');
     return; // Prevent redundant action call
   }
   ```
   This handles expected user behaviors like clicking the same note twice.

This dual approach ensures:
- Programming errors fail fast and visibly (with errors)
- Expected user behaviors are handled gracefully (with NOOP logs)

## Boolean Flags vs. Traditional State Machines

The ModeManager's boolean flags approach differs fundamentally from traditional state machines in several important ways:

### Context Retention

A key advantage of the boolean flags approach is **contextual memory**:

```javascript
// In an action method:
function saveAndSyncNote(noteId) {
  // Set a temporary flag that affects the system
  ModeContext.setLoading(true);
  
  api.saveNote(noteId)
    .then(() => {
      // When done, we can simply unset the flag and KEEP other context
      ModeContext.setLoading(false);
      
      // We're still in editing mode with the current note!
      // We didn't lose our context by entering a "loading state"
      showSuccessNotification(`Note ${ModeContext.currentNoteId} saved`);
    });
}
```

With a traditional state machine:
- Entering a "loading" state would typically EXIT the "editing" state
- You'd need to store what state to return to after loading
- Complex state machines need "history" mechanisms to track this
- Each combination of states becomes its own state (EditingAndLoading, IdleAndLoading, etc.)

### Parallel Concerns

The boolean flags approach naturally models parallel concerns:

```javascript
// These can all be true simultaneously
ModeContext.isEditing     // User is editing a note
ModeContext.isCallingApi  // An API request is in progress
ModeContext.isLoading     // UI is showing a loading indicator
ModeContext.isDirty       // Content has unsaved changes
```

With traditional state machines:
- Each combination becomes a distinct state
- The number of states explodes exponentially
- Transition rules become extremely complex
- Debugging becomes difficult ("why am I in EditingDirtyLoadingState instead of EditingDirtyState?")

### Simpler Validation

With boolean flags, validation rules are simple expressions:

```javascript
// Clear invariants
if (this._editing && !this._currentNoteId) {
  throw new Error('Invariant violation: editing mode is active but no currentNoteId is set');
}
```

With state machines:
- Validation is embedded in transition rules
- It's harder to express invariants that span multiple aspects of state
- Validating becomes more complex as the number of states grows

## Logging System

The ModeManager uses a categorized logging system to make debugging easier:

### Log Categories

- **[ACTION]**: High-level user actions (selectNote, deselectNote)
- **[STATE]**: Individual state changes (editing, currentNoteId)
- **[EVENT]**: Raw DOM events (click, keypress)
- **[NOOP]**: No-operation events (when an action is intentionally skipped)
- **[INIT]**: Component initialization
- **[ERROR]**: Errors and exceptions

All logs are prefixed with `+++ ModeManager` for easy filtering in the console.

### Logging Best Practices

1. Use `logAction()` for high-level operations that affect multiple states
2. Use `logState()` for individual state property changes
3. Use `logDebug()` with the EVENT category for raw DOM events
4. Use `logNoop()` when an event is processed but intentionally ignored
5. Use `logError()` for validation failures and exceptions

## Code Examples

### Event Handler (Processing but not "doing")

```javascript
function handleClick(event) {
  // Determine what was clicked
  const noteContent = event.target.closest('.note-content');
  
  if (noteContent) {
    const noteId = noteContent.closest('.note').dataset.noteId;
    
    // Only call the action if needed (avoid redundant operations)
    if (!ModeContext.isEditing || ModeContext.currentNoteId !== noteId) {
      // Map the event to an action (but don't modify state directly)
      selectNote(noteId);
    } else {
      // Log intentionally ignored operations
      Logger.logNoop('Click in already selected note - no action needed', { noteId });
    }
  }
}
```

### Action Chaining

Some user interactions require multiple actions to execute in sequence. Event handlers can orchestrate this without directly handling state changes:

```javascript
function handleSearchClick(event) {
  // 1. Check if we need to deselect the current note first
  if (ModeContext.isEditing) {
    // Call the deselectNote action to properly exit editing mode
    deselectNote();
  }
  
  // 2. Now focus the search field and enter search mode
  enterSearchMode();
  
  // 3. Log the user's intention at a high level
  Logger.logDebug('User clicked search - chained deselectNote and enterSearchMode', {
    wasEditing: ModeContext.isEditing,
    searchQuery: ModeContext.searchQuery
  }, Logger.LogCategory.EVENT);
}
```

This approach:
- Keeps each action focused on a single responsibility
- Allows event handlers to orchestrate complex sequences
- Maintains proper logging of the intent and sequence
- Preserves the principle that only actions modify state

### Action (The "doing" part)

```javascript
export function selectNote(noteId) {
  // Validate input
  if (!noteId) {
    throw new Error('Cannot select note: noteId is required');
  }
  
  // Check if we're already calling the API
  if (ModeContext.isCallingApi) {
    Logger.logError('Cannot select note while API call is in progress');
    return;
  }
  
  // 1. Update state - mark that we're calling API
  ModeContext.setCallingApi(true);
  
  // 2. Make API call to load note content
  api.fetchNoteContent(noteId)
    .then(content => {
      // 3. Process API response
      
      // 4. Update state with note content and set editing mode
      ModeContext.setCurrentContent(content);
      ModeContext.setCurrentNoteId(noteId);
      ModeContext.setEditing(true);
      
      // 5. UI update - focus the editor
      document.querySelector(`[data-note-id="${noteId}"] .note-content`).focus();
      
      // 6. Final state change - mark API call as complete
      ModeContext.setCallingApi(false);
      
      // 7. Validate the resulting state
      ModeContext.validate();
      
      // 8. Log the action completion
      Logger.logAction('selectNote', { noteId, success: true });
    })
    .catch(error => {
      // Handle errors
      ModeContext.setCallingApi(false);
      Logger.logError(`Failed to select note ${noteId}`, error);
    });
}
```

The example above illustrates how an action can:
1. Validate inputs
2. Change state (multiple times)
3. Make API calls
4. Process responses
5. Update the UI
6. Handle errors
7. Validate state consistency

## Future Considerations

1. **Action Composition**: Complex operations can be built by composing multiple actions
2. **Undo/Redo**: The action pattern makes it easier to implement history tracking
3. **Middleware**: Additional processing can be added between actions and state changes
4. **State Persistence**: The clean separation makes it easier to save/restore state

## Migration Path

The ModeManager is designed to run in parallel with the existing state machine during migration. By using the capture phase for event listeners, it can observe user interactions before the state machine processes them.