# Known Bugs

## Note Saving Issues

1. **Inconsistent Save Behavior on Exit**
   - Steps to reproduce:
     1. Enter to add note
     2. Type "asdf"
     3. Click outside of notes
   - Expected: Note should save (like it does with Escape key)
   - Actual: Note does not save
   - Root cause: Click outside handler doesn't properly set event type before state transition
   - Status: Under investigation

## UI/UX Issues

1. **Note Content Click Detection**
   - Steps to reproduce:
     1. Create a note with multiple lines
     2. Try to click on second line
   - Expected: Click should be detected and cursor should move
   - Actual: Click not detected on nested elements
   - Root cause: Click detection only checked immediate element for note-content class
   - Status: Fixed - Now checks parent elements for note-content class