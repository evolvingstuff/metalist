"""
Core Architecture:
- MIT licensed components only
- Python-based (pip installable or executable)
- Single user per instance (containerization planned for multi-user future)
- FastAPI backend with Pydantic models
- SQLite3 database / SQLAlchemy ORM
- Mako for server-side templating

Data Model & Storage:
- Everything is a note (no separate concept of subnotes)
- Notes can be hierarchically nested
- Notes can be embedded, copied, or linked (future)
- Each note has:
  - uuid: str
  - content: str
  - parent: Optional[str]
  - prev: Optional[str]    # For efficient sibling ordering
  - next: Optional[str]    # For efficient sibling ordering
- Must handle large numbers of notes efficiently (15,000+)
- Per-note encryption at rest
- Server-side encryption/decryption
- Searchable by content or tags or a combo of both
- Tags and other metadata parsed from note content
- Encrypted search indexes persistent across server restarts

Client-Server Communication:
- TLS for non-localhost connections
- Long-polling for updates
- Server maintains knowledge of client's current view
- Server sends minimal diffs using server-side rendering
- Initial load of 50 relevant notes + infinite scroll

Operations & Sync:
Two categories of operations:
1. Immediate operations (sent instantly):
   - Add note
   - Delete note
   - Move note
   - Change note parent

2. Polled operations (batched, sent every X ms):
   - Search updates / tag suggestions
   - Content edits (push on diff)
   - Cross-device sync

Undo/Redo:
- Server-side implementation
- Three basic operations: ADD_NOTE, UPDATE_NOTE, DELETE_NOTE
- In-memory only (doesn't survive server restart)

UI Architecture:
- Minimal JavaScript
- Server-side rendering with Mako templates
- No client-side build step
- Multiple tabs/devices supported via sync
- Editing done using `contenteditable`

The application should optimize for:
- Server-side processing
- Minimal network traffic
- Clean separation of concerns
- Simple, efficient client implementation
- Single source of truth for all relationships

----

# Undo/Redo Design

## Core Operations
Undoable operations:
- Add note
- Move note(s)
- Update note content
- Delete note

## Implementation Approach
- Use command pattern rather than immutable data structures
- Maintain undo stack in server memory only
- No need to persist undo history through server restarts
- No need to encrypt undo history since it's transient

## Content Editing
- Browser handles undo/redo within contenteditable during active editing
- Server updates occur on:
 1. Exiting edit mode
 2. Inactivity timeout (no edits for X seconds)
- This creates more natural undo points at semantic breaks rather than arbitrary intervals

## Search Context
- Search/filter changes clear the undo stack
- No warning shown for stack clearing
- Treat filter changes as context switches, similar to switching documents
- This avoids complex interactions between undo history and search visibility

This approach provides intuitive undo/redo for content operations while avoiding complications with search context and encryption. Using the command pattern allows for clear handling of operations that affect multiple notes (like reordering).

## Implementation Details

### State Capture Approach
- Wrap SQLAlchemy updates to capture note states before any changes
- Maintain in-memory dictionary of original states keyed by transaction UUID
- Only capture first change to each note within a transaction
- After transaction completes, capture final states of all affected notes
- This gives before/after states for everything touched in an operation

### Command Structure
- Single Command class handles all operation types
- Commands store complete before/after states rather than operation-specific logic
- Undo/redo simply restores notes to their previous/next states
- No need for different command types for different operations
- New operations automatically get undo/redo support if they use wrapped updates

### Boundaries and Limitations
- Global operations (affecting large numbers of notes) clear the undo stack
- Similar to how search context changes clear the stack
- Prevents need to hold entire database in memory
- Examples of stack-clearing operations:
 - Bulk tag operations
 - Global find & replace
 - Large imports
 - Operations affecting entire tag hierarchy

### Benefits
- Simpler implementation than operation-specific commands
- More robust - captures all state changes automatically
- Easier to add new operations
- Natural boundaries at global operations
- Only temporary server-side storage needed

## Testing Strategy

### Property-Based Testing with State Hashing
- Start with known initial state and capture hash
- Generate random sequence of operations:
  - Note deletions
  - Content updates
  - Note movements/reordering
- After each operation:
  - Capture hash of entire note set
  - Add hash to verification stack

### Verification Process
1. Undo Testing
   - Step backwards through all operations
   - Compare hash at each step with stored hash
   - Verify return to initial state

2. Redo Testing
   - Step forwards through all operations
   - Compare hash at each step with stored hash
   - Verify arrival at final state

### UI Testing with Cypress
- End-to-end testing of UI interactions
- State machine transition verification
- Cross-reload state preservation testing
- Automated regression testing of core workflows
- Integration with CI pipeline

### Benefits
- Tests system state as a whole rather than individual operations
- Catches unexpected interactions between operations
- Verifies perfect reversibility of operations
- Can run many iterations with different random sequences
- Ensures UI behavior remains consistent across changes

## State Machine Architecture

### Overview
The application uses a finite state machine to manage UI state and user interactions.
Key states are: idle, editing, and searching.

### Components
1. State Machine Controller
   - Coordinates all state machine operations
   - Handles event flow and state transitions
   - Maintains current state and context data

2. Event Mapper
   - Maps raw events to state machine events
   - Context-aware event interpretation
   - State-specific event handling

3. Raw Event Handlers
   - Converts DOM events to normalized events
   - Initial event processing
   - Data extraction

4. Transition Coordinator
   - Manages state transitions
   - Handles enter/exit hooks
   - Validates state changes

### Event Flow
1. DOM Event → Raw Event
2. Raw Event → Mapped Event (with context)
3. Mapped Event → State Transition
4. State Transition → New State

### State Data Management
- Each state maintains its own data
- Data passed through transitions
- Clean separation between states
- Automatic cleanup on state exit

### Benefits
- Clear state boundaries
- Predictable behavior
- Easy debugging
- Modular design
- Testable components

## Encrypted Index Persistence Strategy

Indices use a Write-Ahead Log (WAL) + base index approach:

### Components
1. Base Index
   - Encrypted, compressed snapshot of full index state
   - Written periodically during checkpoints
   - More expensive to write but contains bulk of data

2. Write-Ahead Log (WAL)
   - Append-only log of recent changes
   - Each entry individually encrypted
   - Fast to update (simple append operation)
   - Replayed on startup to recover state

### Operations
- Writes: Append encrypted entry to WAL + update in-memory
- Reads: Serve directly from in-memory index
- Startup: Load base index + replay WAL
- Checkpoint: Write new base index + clear WAL

### Checkpointing Triggers
- Time-based (e.g., every 6 hours)
- Size-based (WAL exceeds X% of base index)
- Clean shutdown

Benefits:
- Fast writes (just WAL append)
- Crash-resistant (WAL replay)
- Efficient storage (compressed base)
- Quick startup (no rebuild needed)
- Automatic recovery from interruption