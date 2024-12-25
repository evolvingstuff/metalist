# Plan for Implementing Undo/Redo Functionality

## UI Event Handlers
- [x] Add event handlers in the UI for `cmd-z` (undo) and `cmd-y` (redo) that trigger alerts for now.

## Command Pattern Setup
- [x] Define a `Command` class to encapsulate undoable operations, storing both pre and post states.
- [x] Implement methods for `execute`, `undo`, and `redo` within the `Command` class.

## State Management
- [ ] Wrap SQLAlchemy updates to capture note states before any changes.
- [ ] Maintain an in-memory dictionary of original states keyed by transaction UUID.
- [ ] Capture final states of all affected notes after a transaction completes.

## Single Command Stack
- [ ] Implement a single stack to store executed commands.
- [ ] Maintain a pointer to track the current position in the command stack for undo/redo operations.

## Server-Side Logic
- [ ] Create server-side endpoints to handle undo and redo requests.
- [ ] Ensure that these endpoints interact with the command pattern to restore previous states.

## Client-Server Communication
- [ ] Update client-side logic to send undo/redo requests to the server.
- [ ] Handle server responses to update the UI accordingly.

## Testing and Verification
- [ ] Implement property-based testing with state hashing to verify undo/redo functionality.
- [ ] Test undo/redo operations for various scenarios, including note deletions, content updates, and note movements.
