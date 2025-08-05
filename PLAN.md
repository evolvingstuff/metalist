# Multi-Device Synchronization Plan

## Overview
Enable simultaneous use across multiple devices/browsers with real-time synchronization and conflict prevention.

## Core Components

### 1. Client Identity System
- Generate unique UUID for each browser tab/device on page load
- Store in sessionStorage (unique per tab) or localStorage with tab ID
- Send client UUID with every request to server

### 2. Server-Side State Tracking
- Track global "last update UUID" for the entire note database
- Generate new update UUID whenever any change occurs (create, edit, delete, move)
- Store client lock information (which client is editing which note)

### 3. Synchronization Protocol
- Server includes current update UUID in all responses
- Client stores last known update UUID
- Long polling to check for updates every N seconds
- If UUIDs don't match → trigger refresh

### 4. Edit Locking Mechanism
- When client opens note for editing → acquire lock on server
- Other clients see locked notes as read-only with indicator
- Lock released when:
  - Note saved
  - Edit mode exited (Escape)
  - Client disconnects/timeout

## Implementation Details

### Client-Side Changes

#### Page Load
```javascript
// Generate unique client ID
const CLIENT_ID = sessionStorage.getItem('client_id') || crypto.randomUUID();
sessionStorage.setItem('client_id', CLIENT_ID);

// Store last known update UUID
let lastUpdateUUID = null;
```

#### Long Polling Timer
```javascript
setInterval(() => {
    if (!ModeContext.isEditing) {  // Only poll when not editing
        checkForUpdates();
    }
}, 5000);  // Check every 5 seconds

async function checkForUpdates() {
    const response = await fetch('/api/check-updates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            clientId: CLIENT_ID, 
            lastUpdateUUID: lastUpdateUUID 
        })
    });
    
    if (response.status === 200) {
        const data = await response.json();
        if (data.needsUpdate) {
            lastUpdateUUID = data.currentUpdateUUID;
            refreshNotesView();
        }
    }
}
```

#### Edit Lock Management
```javascript
// When entering edit mode
async function enterEditMode(noteId) {
    const response = await fetch('/api/acquire-lock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            noteId, 
            clientId: CLIENT_ID,
            lastUpdateUUID: lastUpdateUUID
        })
    });
    
    if (!response.ok) {
        alert('Note is being edited by another device');
        return false;
    }
    
    // Continue with edit mode...
}

// When exiting edit mode
async function exitEditMode(noteId) {
    await fetch('/api/release-lock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            noteId, 
            clientId: CLIENT_ID,
            lastUpdateUUID: lastUpdateUUID
        })
    });
}
```

### Server-Side Changes

#### New Database Tables
```sql
-- Track global state
CREATE TABLE sync_state (
    id INTEGER PRIMARY KEY,
    last_update_uuid TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Track note locks
CREATE TABLE note_locks (
    note_id INTEGER PRIMARY KEY,
    client_id TEXT NOT NULL,
    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (note_id) REFERENCES notes(id)
);
```

#### Update UUID Generation
```python
import uuid

def generate_update_event():
    """Call this whenever any change occurs"""
    new_uuid = str(uuid.uuid4())
    db.execute("UPDATE sync_state SET last_update_uuid = ?, updated_at = CURRENT_TIMESTAMP", 
               (new_uuid,))
    return new_uuid
```

#### New API Endpoints
```python
@app.route('/api/check-updates')
def check_updates():
    client_id = request.headers.get('X-Client-ID')
    last_known = request.headers.get('X-Last-Update')
    
    current_uuid = db.execute("SELECT last_update_uuid FROM sync_state").fetchone()[0]
    
    return jsonify({
        'needsUpdate': last_known != current_uuid,
        'currentUpdateUUID': current_uuid
    })

@app.route('/api/acquire-lock', methods=['POST'])
def acquire_lock():
    data = request.json
    note_id = data['noteId']
    client_id = data['clientId']
    
    # Check if already locked by different client
    existing = db.execute("SELECT client_id FROM note_locks WHERE note_id = ?", 
                         (note_id,)).fetchone()
    
    if existing and existing[0] != client_id:
        return jsonify({'error': 'Note locked by another client'}), 409
    
    # Acquire/refresh lock
    db.execute("INSERT OR REPLACE INTO note_locks (note_id, client_id) VALUES (?, ?)",
               (note_id, client_id))
    
    generate_update_event()  # Notify other clients
    return jsonify({'success': True})

@app.route('/api/release-lock', methods=['POST']) 
def release_lock():
    data = request.json
    note_id = data['noteId']
    client_id = data['clientId']
    
    db.execute("DELETE FROM note_locks WHERE note_id = ? AND client_id = ?",
               (note_id, client_id))
    
    generate_update_event()  # Notify other clients
    return jsonify({'success': True})
```

#### Modify Existing Endpoints
```python
# Add to ALL API endpoints - every request should include client context
def save_note():
    data = request.json
    client_id = data.get('clientId')  # Extract from JSON body
    last_known = data.get('lastUpdateUUID')  # Extract from JSON body
    
    # ... existing save logic ...
    
    new_uuid = generate_update_event()  # Generate new UUID
    
    return jsonify({
        'success': True,
        'updateUUID': new_uuid,
        'locks': get_current_locks()  # For UI indicators
    })

# Similarly update ALL other endpoints:
# - /api/notes (GET/POST)
# - /api/notes/<id> (PUT/DELETE) 
# - /api/notes/<id>/move
# - /api/search
# - etc.
```

### UI Indicators

#### Locked Note Display
```css
.note.locked {
    opacity: 0.6;
    border-left: 3px solid #ff6b6b;
}

.note.locked::after {
    content: "🔒 Editing on another device";
    font-size: 12px;
    color: #ff6b6b;
}
```

#### Sync Status Indicator
```html
<div id="sync-status" class="sync-indicator">
    <span class="sync-dot"></span>
    <span class="sync-text">Synced</span>
</div>
```

## Edge Cases & Considerations

### Network Issues
- Handle offline/online detection
- Queue changes when offline, sync when reconnected
- Show "offline" indicator

### Lock Timeouts
- Auto-release locks after N minutes of inactivity
- Heartbeat mechanism to keep locks alive
- Handle client crashes/browser closes

### Conflict Resolution
- If two clients edit simultaneously (race condition)
- Last-write-wins strategy with user notification
- Potentially show diff/merge UI

### Performance
- Batch multiple rapid changes into single update UUID
- Debounce update generation (don't generate UUID for every keystroke)
- Consider WebSocket upgrade for real-time updates

## Implementation Phases

### Phase 1: Basic Sync (No Locking)
1. Add client UUID generation
2. Add update UUID tracking
3. Implement long polling
4. Test multi-device refresh

### Phase 2: Edit Locking
1. Add lock/unlock API endpoints
2. Implement acquire/release lock on edit
3. Add locked note UI indicators
4. Test lock behavior

### Phase 3: Polish & Edge Cases
1. Handle network issues
2. Add lock timeouts
3. Improve UI indicators
4. Performance optimizations

## Questions to Consider

1. **Update Granularity**: Should we track updates per-note or globally?
2. **Lock Duration**: How long should locks last? Auto-release timeout?
3. **Conflict UI**: How to handle/display conflicts to users?
4. **Offline Support**: Should changes be queued when offline?
5. **WebSocket Upgrade**: Move from polling to real-time WebSocket?

## Files to Modify

### Client-Side
- `app/static/js/modules/mode-manager/mode-context.js` - Add client ID generation
- `app/static/js/modules/mode-manager/actions/note-actions.js` - Add client ID to all requests
- `app/static/js/modules/mode-manager/actions/ui-actions.js` - Add client ID to refresh calls
- `app/static/js/modules/mode-manager/events/search-events.js` - Add client ID to search
- `app/static/js/modules/config.js` - Sync polling interval
- `app/templates/base.html` - Sync status indicator
- `app/static/css/main.css` - Lock/sync styling

### Server-Side  
- `app.py` - New API endpoints
- `database/schema.sql` - New tables
- `services/note_service.py` - Update UUID generation
- New: `services/sync_service.py` - Sync logic
- New: `services/lock_service.py` - Lock management

This plan provides a solid foundation for multi-device sync. Should we start with Phase 1?