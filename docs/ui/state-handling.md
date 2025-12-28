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

## Asynchronous Code Pattern

The ModeManager uses the `async/await` pattern for all asynchronous operations rather than Promise chains:

### Key Benefits

1. **Linear Code Flow**: Code executes top-to-bottom in a more readable and maintainable way
2. **Better Error Propagation**: Errors naturally propagate up the call stack when not caught
3. **Simplified Variable Scoping**: Variables are accessible throughout the entire function
4. **Reduced Nesting**: Eliminates the "pyramid of doom" from nested Promise chains
5. **Improved Debugging**: Error stack traces are more accurate and meaningful

### Implementation Guidelines

```javascript
// DO: Use async/await
export async function saveNote(noteId) {
  // Validation
  if (!noteId) {
    throw new Error('Cannot save note: noteId is required');
  }
  
  // Set loading state
  ModeContext.setLoading(true);
  
  // Call API and await result
  const response = await NotesAPI.saveNote(noteId, contentHTML);
  
  // Update state after API call
  ModeContext.setLastSavedContent(contentHTML);
  ModeContext.setDirty(false);
  
  // Clear loading state
  ModeContext.setLoading(false);
  
  return response;
}

// DON'T: Use Promise chains
export function saveNote(noteId) {
  // Validation
  if (!noteId) {
    throw new Error('Cannot save note: noteId is required');
  }
  
  // Set loading state
  ModeContext.setLoading(true);
  
  // Call API with Promise chain
  return NotesAPI.saveNote(noteId, contentHTML)
    .then(response => {
      // Update state in nested callback
      ModeContext.setLastSavedContent(contentHTML);
      ModeContext.setDirty(false);
      
      // Clear loading state
      ModeContext.setLoading(false);
      
      return response;
    });
}
```

### Rule of Thumb

* All asynchronous functions should be marked with `async` keyword
* Use `await` for all Promise-returning function calls
* Avoid `try/catch` blocks to maintain fail-fast behavior when errors occur
* Never use `.then()`, `.catch()`, or `.finally()` methods in new code

This pattern works particularly well with our "Always Be Changin'" (ABC) validation approach, as the linear flow makes state transitions more explicit and easier to follow.

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
         actionSelectNote(noteId);
      } else {
         // Log intentionally ignored operations
         Logger.logNoop('Click in already selected note - no action needed', {noteId});
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
      actionDeselectNote();
   }

   // 2. Now focus the search field and enter search mode
   actionEnterSearchMode();

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
export async function selectNote(noteId) {
  // Validation
  if (!noteId) {
    throw new Error('Cannot select note: noteId is required');
  }
  
  // Check if we're already calling the API
  if (ModeContext.isCallingApi) {
    Logger.logError('Cannot select note while API call is in progress');
    return;
  }
  
  // 1. Update state - mark that we're calling API
  ModeContext.setLoading(true);
  
  // 2. Make API call to load note content
  const response = await api.fetchNoteContent(noteId);
  
  // 3. Process API response
  
  // 4. Update state with note content and set editing mode
  ModeContext.setCurrentContent(response.content);
  ModeContext.setCurrentNoteId(noteId);
  ModeContext.setEditing(true);
  
  // 5. UI update - focus the editor
  document.querySelector(`[data-note-id="${noteId}"] .note-content`).focus();
  
  // 6. Final state change - mark API call as complete
  ModeContext.setLoading(false);
  
  // 7. Validate the resulting state
  ModeContext.validate();
  
  // 8. Log the action completion
  Logger.logAction('selectNote', { noteId, success: true });
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

## Multi-Tab Extension

The ModeManager architecture naturally supports extending to multi-tab search contexts without breaking the core design principles.

### Tab State Integration

Tabs add a **minimal layer** above the existing global ModeContext and the
server keeps that structure hot in memory, so browser restarts no longer lose
search contexts:

```javascript
// Existing global state (shared across tabs)
ModeContext = {
  // These remain global - never edit in background tabs
  editing: false,
  loading: false, 
  isDirty: false,
  currentNoteId: null,
  clipboardNoteId: '456',
  
  // New tab management
  activeTabId: 'work',
  tabs: {
    'work': { searchQuery: 'project alpha', scrollY: 150 },
    'personal': { searchQuery: 'recipes', scrollY: 0 }
  }
}
```

- `tab-state-service.js` fetches `/api2/notes/tab-state` on startup and hydrates
  `ModeContext` so the UI mirrors whatever the previous window last displayed.
- Scroll/search changes are throttled (≈1 Hz) and POSTed back so the cache stays
  aligned with the DOM without spamming requests.
- With a single interactive client, this global cache keeps persistence simple:
  new browser windows immediately reuse the stored tabs.

### Event-Driven Tab Switching

The event → action → state pattern handles tabs naturally:

```javascript
function handleTabSwitch(newTabId) {
  // Event handler determines intent
  if (ModeContext.activeTabId === newTabId) {
    Logger.logNoop('Tab already active', {tabId: newTabId});
    return;
  }
  
  // Action orchestrates the complex operation
  actionSwitchToTab(newTabId);
}

async function actionSwitchToTab(newTabId) {
  // 1. Save current context
  saveCurrentTabContext();
  
  // 2. Clean up current state (no background editing)
  if (ModeContext.isEditing) {
    await actionSaveAndDeselect();
  }
  
  // 3. Switch tab context
  ModeContext.setActiveTab(newTabId);
  
  // 4. Restore new context  
  await actionRefreshView();
  restoreTabScrollPosition();
}
```

### Undo/Redo with Tab Context

Commands capture **complete application snapshots** for time-travel debugging:

```javascript
// In BaseTransactionService (backend)
class Command {
  constructor(operation, changes) {
    this.operation = operation;
    this.changes = changes;
    
    // Frontend passes complete tab snapshot
    this.tabSnapshot = frontendTabContext;
  }
}

// Undo restores exact moment in time
async function actionUndo() {
  const command = UndoStack.peek();
  
  // Restore complete tab state from when action was taken
  ModeContext.setActiveTab(command.tabSnapshot.activeTabId);
  ModeContext.setTabs(command.tabSnapshot.tabs);
  
  // Execute undo and show user exactly what happened
  await command.undo();
  await actionRefreshView();
}
```

### Multi-Client Context Management

The server-side undo system automatically handles multiple browser tabs and devices through context boundaries:

```javascript
// Client sends context with every operation
async function actionCreateNote() {
  const clientContext = {
    tabId: ModeContext.activeTabId,
    sessionId: browserSessionId,
    clientId: deviceId
  };
  
  await NotesAPI.createNote(parentId, { context: clientContext });
}

// Connectivity-only polling (single active session = no remote diffing)
async function pollForConnectivity() {
  const authToken = localStorage.getItem('auth_token');
  const response = await fetch('/api2/auth/status', {
    method: 'GET',
    headers: authToken ? { 'Authorization': `Bearer ${authToken}` } : {}
  });

  if (response.ok) {
    ErrorHandler.handleConnectionRestored();
  }
}
```

The background poll now exists purely to clear network banners once connectivity returns. Remote diffing is unnecessary because the auth service issues only one session token at a time.

**Context Boundary Rules:**
- **Tab switches**: Clear undo stack (new search context)
- **Client switches**: Clear undo stack (different browser/device)  
- **Remote operations**: Clear undo stack (changes from other client)
- **App reload**: Clear undo stack (new session)

**Note-Level Locking Integration:**
```javascript
// Enter edit mode with locking
async function actionSelectNote(noteId) {
  try {
    // Acquire exclusive lock on note
    await NotesAPI.acquireNoteLock(noteId, clientContext);
    
    // Stop background polling to prevent UI shifts
    clearInterval(pollInterval);
    
    // Enter editing state
    ModeContext.setCurrentNoteId(noteId);
    ModeContext.setEditing(true);
    
  } catch (error) {
    if (error.status === 423) {
      showNotification("This note is being edited by another user");
      return;
    }
    throw error;
  }
}

// Exit edit mode with sync
async function actionDeselectNote() {
  // Save and release lock
  await actionSaveNote(ModeContext.currentNoteId);
  await NotesAPI.releaseNoteLock(ModeContext.currentNoteId, clientContext);
  
  // Refresh with all changes that happened during editing
  await actionRefreshView();
  
  // Resume background polling
  startPolling();
  
  // Exit editing state
  ModeContext.setEditing(false);
  ModeContext.setCurrentNoteId(null);
}
```

**Lock Protection Rules:**
- Cannot edit notes locked by other users
- Cannot delete notes (or their children) locked by other users
- Cannot move notes locked by other users
- Lock timeouts handle crashed/disconnected clients

This eliminates all undo/redo conflicts while maintaining predictable behavior - users can only undo operations from their current working context. The locking system ensures stable editing sessions without UI interference from concurrent users.

### Design Benefits Preserved

The tab extension **maintains all core ModeManager principles**:

1. **Single Global State**: ModeContext remains the single source of truth
2. **Fail-Fast Validation**: Tab switching triggers full state validation  
3. **Event-Driven Flow**: Tab operations follow event → action → state pattern
4. **Transparent Debugging**: All tab state visible in single object inspection
5. **Action Composition**: Complex tab operations compose existing actions

### Implementation Strategy

- **Phase 1**: Add tab properties to ModeContext, persist via `/api2/notes/tab-state`
- **Phase 2**: Implement tab switching actions using existing patterns
- **Phase 3**: Extend undo commands to capture tab snapshots  
- **Phase 4**: Add tab UI components and keyboard shortcuts

The event-driven architecture makes this extension **additive rather than disruptive** - existing code continues to work while new tab functionality layers on top.

## Future Considerations

1. **Action Composition**: Complex operations can be built by composing multiple actions
2. **Undo/Redo**: The action pattern makes it easier to implement history tracking
3. **Middleware**: Additional processing can be added between actions and state changes
4. **State Persistence**: The clean separation makes it easier to save/restore state

## Migration Path

The ModeManager is designed to run in parallel with the existing state machine during migration. By using the capture phase for event listeners, it can observe user interactions before the state machine processes them.
