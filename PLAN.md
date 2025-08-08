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
- **Clipboard stores serialized note data, NOT database notes**
- Client never stores clipboard state

### Copy Operation (Cmd+C)
1. Client sends copy request to server with source note ID
2. **Server serializes note tree to in-memory data structure** (no database writes)
3. Server stores this serialized data in client's server-side clipboard
4. Copy is independent snapshot - immune to future edits of original

### Paste Operation (Cmd+V / Shift+Cmd+V)  
1. Client sends paste request (no note IDs needed)
2. Server deserializes clipboard data into fresh database notes
3. Server positions new notes at target location with proper parent IDs
4. **Server re-serializes original clipboard data for future pastes** (keeps clean template)
5. Clipboard always contains the original template, not pasted notes

### Benefits
- **True copy semantics**: Copy creates independent snapshot immediately
- **Multiple pastes**: Each paste gets fresh copy from stable template
- **No cycles**: Each paste creates new UUIDs, preventing self-reference
- **Edit immunity**: Clipboard copy immune to original note changes
- **Server-side state**: No client-side clipboard synchronization issues
- **No orphaned database notes**: Clipboard is pure in-memory data

## Implementation Plan

1. **Create `copy_note_in_memory()` function** - serializes note tree without database writes
2. **Create `paste_note_from_memory()` function** - deserializes and creates real database notes
3. **Add server-side clipboard storage** (per client ID) for serialized data
4. **Create `/api/notes/copy` endpoint** - uses `copy_note_in_memory()`
5. **Update `/api/notes/paste-*` endpoints** - use `paste_note_from_memory()`
6. **Remove client-side clipboard logic** from frontend
7. **Update frontend copy/paste actions** to use new endpoints

## Key Insight: Clipboard Must Be Pure Data

**CRITICAL**: The clipboard must store serialized note data structures, not database note IDs. Creating database notes for clipboard creates orphaned records that break the tree structure constraints.

## Additional Issue: Clipboard Mode Tracking

**PROBLEM DISCOVERED**: When editing a note, Cmd+C/Cmd+V behavior depends on text selection:
- **Text selected**: Should use system clipboard for text copy/paste
- **No text selected**: Should use note clipboard for note copy/paste

**SOLUTION NEEDED**: Client-side clipboard mode tracking:

### Copy Behavior (Cmd+C)
- **If text selected in editor**: 
  - Set clipboard mode = 'system'
  - Allow default browser text copy
  - Do NOT call server
- **If no text selected**: 
  - Set clipboard mode = 'note'  
  - Call server copy endpoint
  - preventDefault to avoid system clipboard interference

### Paste Behavior (Cmd+V)  
- **If clipboard mode = 'system'**:
  - Allow default browser text paste into editor
- **If clipboard mode = 'note'**:
  - Call server paste endpoint
  - preventDefault to avoid system clipboard interference
  - Trigger UI refresh (like other content-modifying operations)

### Implementation Requirements
1. Add `clipboardMode` state to ModeContext ('system' vs 'note')
2. Update copy handler to check text selection and set mode
3. Update paste handler to check mode and route appropriately
4. Ensure mode resets appropriately (e.g., when switching notes)

## Migration Notes

This is a breaking change to the copy/paste system but fixes fundamental architectural problems that made the feature unreliable. The previous attempt failed because it created real database notes for clipboard storage. The current implementation works for server-side clipboard but needs client-side mode tracking for proper text vs note distinction.