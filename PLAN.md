# Fix Copy/Paste Architecture

## Current Broken Architecture

The copy/paste system is fundamentally broken:

1. **Copy (Cmd+C)**: Only stores original note ID in client-side clipboard (`ModeContext.clipboardNoteId`)
2. **Paste**: Creates the actual copy with new UUIDs at paste time
3. **Result**: After first paste, clipboard contains the newly created note ID, leading to "paste into self" cycles

## Problems with Current Approach

1. **No actual copying on copy**: Copy operation is just client-side state management
2. **Copy happens too late**: Actual copying with new UUIDs happens at paste time
3. **Clipboard corruption**: After paste, clipboard points to the pasted note instead of maintaining a clean template
4. **Edit corruption**: If original note is edited after copy, there's no independent copy to paste from
5. **Self-paste cycles**: Trying to paste a note into itself creates infinite recursion

## Target Architecture

### Server-Side Clipboard Storage
- Each client maintains server-side clipboard state (not client-side)
- Clipboard stores actual independent copies with new UUIDs
- Client never stores clipboard state

### Copy Operation (Cmd+C)
1. Client sends copy request to server with source note ID
2. Server creates full recursive copy with new UUIDs immediately 
3. Server stores this copy in client's server-side clipboard
4. Copy is independent snapshot - immune to future edits of original

### Paste Operation (Cmd+V / Shift+Cmd+V)  
1. Client sends paste request (no note IDs needed)
2. Server uses current clipboard copy
3. Server positions clipboard copy at target location
4. Server creates NEW copy from original clipboard template for future pastes
5. Server updates client clipboard with the fresh copy

### Benefits
- **True copy semantics**: Copy creates independent snapshot immediately
- **Multiple pastes**: Each paste gets fresh copy from stable template
- **No cycles**: Each paste creates new UUIDs, preventing self-reference
- **Edit immunity**: Clipboard copy immune to original note changes
- **Server-side state**: No client-side clipboard synchronization issues

## Implementation Plan

1. **Add server-side clipboard storage** (per client ID)
2. **Create `/api/notes/copy` endpoint** - creates copy immediately 
3. **Update `/api/notes/paste-*` endpoints** - use clipboard, create fresh copies
4. **Remove client-side clipboard logic** from frontend
5. **Update frontend copy/paste actions** to use new endpoints

## Migration Notes

This is a breaking change to the copy/paste system but fixes fundamental architectural problems that made the feature unreliable.