# Copy and Paste Functionality for MetaList3

## Overview

This plan outlines the implementation of copy/paste functionality for hierarchical notes in MetaList3. The feature will add two key API endpoints:

1. `paste_sibling(source_note_id, target_note_id)` - Pastes a copy of a note and all its descendants as a sibling after the target note
2. `paste_child(source_note_id, target_note_id)` - Pastes a copy of a note and all its descendants as the first child of the target note

## Implementation Plan

### 1. Core Helper Function: `copy_note`

First, we'll implement a helper function in the `LinkedListManager` class that handles the recursive copying of a note and all its descendants:

```python
@staticmethod
def copy_note(db: Session, note_id: str, new_parent_id: Optional[str] = None) -> str:
    """
    Creates a deep copy of a note and all its descendants.
    
    Args:
        db: Database session
        note_id: ID of the note to copy
        new_parent_id: Optional parent ID for the copied note
        
    Returns:
        ID of the new copied root note
    """
    # 1. Get the original note
    # 2. Create a new note with the same content but new ID (UUID)
    # 3. Set created_at and updated_at to current time
    # 4. Map old IDs to new IDs to maintain hierarchy
    # 5. Recursively copy all children, updating their parent_ids
    # 6. Return the new root note ID
```

### 2. API Endpoints

We'll then add two new API endpoints in the notes.py file:

```python
@router.post("/{source_note_id}/paste-sibling/{target_note_id}")
@delay_response_decorator
@api_transaction_decorator
@db_transaction_decorator
def paste_sibling(source_note_id: str, target_note_id: str, db: Session = Depends(get_db)):
    """Paste a copy of source_note and its descendants as a sibling after target_note"""
    # Implementation details
```

```python
@router.post("/{source_note_id}/paste-child/{target_note_id}")
@delay_response_decorator
@api_transaction_decorator
@db_transaction_decorator
def paste_child(source_note_id: str, target_note_id: str, db: Session = Depends(get_db)):
    """Paste a copy of source_note and its descendants as the first child of target_note"""
    # Implementation details
```

### 3. Implementation Steps for the `copy_note` Function

1. **Validate Source Note**:
   - Check if the source note exists
   - Retrieve its content and structure

2. **Create Initial Copy**:
   - Generate a new UUID for the copied note (all copies get new IDs)
   - Create a new DBNote with the same content but new ID
   - Set created_at and updated_at timestamps to current time
   - Initially, it won't be connected to the list structure

3. **ID Mapping**:
   - Create a mapping from original IDs to new IDs (for all descendant notes)
   - This mapping will be used to update parent/child relationships

4. **Recursive Copy Algorithm**:
   - Build a function that copies a note and recursively copies all its children
   - For each note:
     - Create a new note with a new UUID
     - Set fresh timestamps for the new note
     - Add the ID mapping (old ID → new ID)
     - Get all children of the original note
     - Recursively copy each child, updating parent_id to point to the new parent

5. **Maintain Sibling Order**:
   - Preserve the same ordering (prev_id/next_id links) between siblings in the copy
   - Use the ID mapping to set up the correct links

### 4. Implementation Steps for Paste Endpoints

#### For `paste_sibling`:
1. Use `copy_note` to create a deep copy of the source note and its descendants
2. Get the target note to determine its parent
3. Use `move_note` to position the copied note as a sibling after the target:
   ```python
   LinkedListManager.move_note(
       db=db,
       note_id=new_root_note_id,  # ID returned from copy_note
       new_parent_id=target_note.parent_id,
       sibling_id=target_note_id,
       position=MovePosition.AFTER
   )
   ```

#### For `paste_child`:
1. Use `copy_note` to create a deep copy of the source note and its descendants
2. Use `move_note` to position the copied note as a child of the target:
   ```python
   LinkedListManager.move_note(
       db=db,
       note_id=new_root_note_id,  # ID returned from copy_note
       new_parent_id=target_note_id,
       sibling_id=None,
       position=None
   )
   ```

### 5. Edge Cases and Error Handling

- **Self-Reference**: Prevent a note from being pasted as its own sibling or child
- **Circular Reference**: Ensure no circular parent-child relationships are created
- **Non-Existent Notes**: Handle cases where source or target notes don't exist
- **Maintaining List Integrity**: Ensure the linked list structure remains valid
- **Transaction Safety**: Use appropriate transaction isolation to prevent corruption

## UI Implementation

After implementing the backend functionality for copying and pasting notes, we'll now add UI actions to expose this functionality to users via intuitive keyboard shortcuts.

### 1. Update ModeContext

First, we'll update the ModeContext to track the currently copied note:

```javascript
// In mode-context.js
class ModeContext {
    // Existing properties...
    
    // New property to track copied note
    _clipboardNoteId = null;
    
    // Getter and setter
    get clipboardNoteId() {
        return this._clipboardNoteId;
    }
    
    setClipboardNoteId(id) {
        // Handle null - clear clipboard
        if (id === null) {
            console.log("Clearing clipboard note ID");
            this._clipboardNoteId = null;
            return;
        }
        
        // Only update if changing to prevent redundant updates
        if (this._clipboardNoteId !== id) {
            console.log(`Setting clipboard note ID to: ${id}`);
            this._clipboardNoteId = id;
        }
    }
}
```

### 2. Add Action Functions

Next, we'll implement three action functions for copying and pasting notes:

```javascript
// In keyboard-events.js or a new copy-paste-actions.js

function actionCopyNote() {
    // Get the currently edited note ID
    const currentNoteId = ModeContext.currentNoteId;
    
    // Only proceed if we're editing a note
    if (!ModeContext.isEditing || !currentNoteId) {
        console.log("Cannot copy note: No note is being edited");
        return;
    }
    
    // Check if text is selected
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed) {
        // Text is selected, let default copy behavior handle it
        console.log("Text selection detected, using default copy behavior");
        return;
    }
    
    // Save the note ID to clipboard
    ModeContext.setClipboardNoteId(currentNoteId);
    console.log(`Copied note with ID: ${currentNoteId}`);
    
    // Optional: Provide visual feedback to user
    showToast("Note copied!");
}

async function actionPasteNoteSibling() {
    // Get the currently edited note ID and clipboard note ID
    const currentNoteId = ModeContext.currentNoteId;
    const clipboardNoteId = ModeContext.clipboardNoteId;
    
    // Validate we have both required IDs
    if (!ModeContext.isEditing || !currentNoteId) {
        console.log("Cannot paste note: No target note is being edited");
        return;
    }
    
    if (!clipboardNoteId) {
        console.log("Cannot paste note: No note has been copied");
        showToast("Nothing to paste! Copy a note first.");
        return;
    }
    
    // Call the API to paste as sibling
    try {
        const response = await fetch(`/api2/notes/${clipboardNoteId}/paste-sibling/${currentNoteId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`Failed to paste note: ${response.statusText}`);
        }
        
        const result = await response.json();
        console.log(`Pasted note as sibling with new ID: ${result.id}`);
        
        // Refresh the notes list
        await refreshNotesList();
        
        // Optional: Provide visual feedback
        showToast("Note pasted as sibling!");
    } catch (error) {
        console.error("Error pasting note as sibling:", error);
        showToast("Failed to paste note");
    }
}

async function actionPasteNoteChild() {
    // Get the currently edited note ID and clipboard note ID
    const currentNoteId = ModeContext.currentNoteId;
    const clipboardNoteId = ModeContext.clipboardNoteId;
    
    // Validate we have both required IDs
    if (!ModeContext.isEditing || !currentNoteId) {
        console.log("Cannot paste note: No target note is being edited");
        return;
    }
    
    if (!clipboardNoteId) {
        console.log("Cannot paste note: No note has been copied");
        showToast("Nothing to paste! Copy a note first.");
        return;
    }
    
    // Call the API to paste as child
    try {
        const response = await fetch(`/api2/notes/${clipboardNoteId}/paste-child/${currentNoteId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`Failed to paste note: ${response.statusText}`);
        }
        
        const result = await response.json();
        console.log(`Pasted note as child with new ID: ${result.id}`);
        
        // Refresh the notes list
        await refreshNotesList();
        
        // Optional: Provide visual feedback
        showToast("Note pasted as child!");
    } catch (error) {
        console.error("Error pasting note as child:", error);
        showToast("Failed to paste note");
    }
}
```

### 3. Add Keyboard Event Handlers

Finally, we'll add keyboard event handlers for the copy/paste shortcuts:

```javascript
// In keyboard-events.js

function handleKeyDown(event) {
    // Existing key handlers...
    
    // Handle copy (Cmd/Ctrl+C)
    if ((event.metaKey || event.ctrlKey) && event.key === 'c') {
        // We let the default copy behavior happen for text selection
        // But also try our note copy action which will only activate 
        // if there's no text selection
        actionCopyNote();
        return;
    }
    
    // Handle paste as sibling (Cmd/Ctrl+V)
    if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key === 'v') {
        // Check if an input element is focused
        const activeEl = document.activeElement;
        const isInputFocused = activeEl.tagName === 'INPUT' || 
                              activeEl.tagName === 'TEXTAREA' || 
                              activeEl.isContentEditable;
        
        // If we're in an input field, we need to be careful not to interfere with normal paste
        if (isInputFocused) {
            // Get selection info
            const selection = window.getSelection();
            const hasTextSelected = selection && !selection.isCollapsed;
            
            if (hasTextSelected || !ModeContext.clipboardNoteId) {
                // Let default paste behavior handle this
                return;
            }
            
            // Prevent default paste for note pasting
            event.preventDefault();
        }
        
        actionPasteNoteSibling();
        return;
    }
    
    // Handle paste as child (Shift+Cmd/Ctrl+V)
    if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key === 'v') {
        event.preventDefault(); // Always prevent default for this combo
        actionPasteNoteChild();
        return;
    }
}
```

### 4. Edge Cases and Additional Features

- **Clipboard Persistence**: Consider how long the clipboard note ID should persist
- **Visual Feedback**: Add indicators to show when a note is copied
- **Paste Button**: Add UI buttons for pasting in addition to keyboard shortcuts
- **Empty Clipboard Handling**: Clear feedback when trying to paste without copying first
- **Error Handling**: Proper user feedback for API failures

## Future Enhancements

- Add a "cut" operation that moves rather than copies
- Implement a clipboard to hold multiple copied notes
- Allow pasting at specific positions (not just after or as first child)
- Add support for cross-session clipboard persistence
