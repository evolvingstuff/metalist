# Fix Dead Client Lock Problem

## Current Problem

**Scenario:**
1. Client A starts editing note 1 ’ acquires lock, note shows as locked to other clients
2. Client A shuts down browser without properly releasing lock
3. Server never receives lock release signal
4. Note 1 remains locked forever, blocking all other clients

**Root Cause:**
- Locks are only released on explicit client action (`release-lock` API call)
- No mechanism to detect dead/disconnected clients
- Editing clients don't send heartbeats (sync polling is disabled while editing)

## Solution: Editing Client Heartbeat System

### Overview
Implement a separate heartbeat system specifically for editing clients that:
- Sends periodic "still alive" signals while editing
- Includes note ID to prevent lock leakage when switching notes
- Allows server to expire locks from dead clients quickly

### Technical Design

#### Server-Side Changes

1. **Enhanced Lock Storage**
   ```typescript
   // Current: {note_id: client_id}
   _note_locks: Dict[str, str] = {}
   
   // New: {note_id: {client_id: string, timestamp: number}}
   _note_locks: Dict[str, Dict[str, Any]] = {}
   ```

2. **Lock Timestamp Tracking**
   - Store acquisition/refresh timestamp with each lock
   - Update timestamp on heartbeat from correct client + note combination

3. **Lock Expiration Logic**
   - Check lock age when acquiring locks
   - Expire locks older than 5 seconds (allows for network delays)
   - Clean up expired locks automatically

4. **API Changes**
   - Reuse existing `/api/notes/acquire-lock` for heartbeat refresh
   - Add timestamp validation to prevent lock leakage

#### Client-Side Changes

1. **Editing Heartbeat Timer**
   ```javascript
   // Start heartbeat when entering edit mode
   setInterval(() => {
     if (isEditing && currentNoteId) {
       sendEditingHeartbeat(currentNoteId);
     }
   }, 1000);
   ```

2. **Heartbeat Management**
   - Start heartbeat timer on edit mode entry
   - Stop heartbeat timer on edit mode exit
   - Send note ID + client ID in each heartbeat
   - Handle heartbeat failures gracefully

3. **Note Switching Logic**
   ```
   switchToEditNote(newNoteId):
     1. Stop current heartbeat (if any)
     2. Release current lock (if any) 
     3. Acquire lock on new note
     4. Start heartbeat for new note
   ```

### Implementation Steps

1. **Update server lock storage structure** with timestamps
2. **Add lock expiration checking** to acquire-lock endpoint
3. **Implement client-side heartbeat timer** in editing mode
4. **Update note switching logic** to manage heartbeats properly
5. **Add heartbeat failure handling** and user feedback
6. **Test dead client scenarios** and lock expiration timing

### Benefits

- **Fast dead client detection**: 5-second timeout vs infinite waiting
- **Prevents lock leakage**: Note ID included in heartbeat prevents wrong locks being refreshed
- **Minimal overhead**: 1 heartbeat/second only while editing
- **Backwards compatible**: Existing lock acquire/release logic unchanged
- **Self-healing**: System automatically recovers from dead clients

### Edge Cases Handled

1. **Rapid note switching**: Each note gets its own lock lifecycle
2. **Network interruption**: Locks expire and allow recovery
3. **Browser crash**: Dead client locks expire automatically
4. **Clock skew**: Use reasonable timeout window (5 seconds)
5. **Race conditions**: Timestamp-based lock ownership prevents conflicts

## Migration Notes

This is an additive change that enhances the existing lock system without breaking current functionality. The heartbeat system provides a safety net for cases where the normal lock release flow fails.