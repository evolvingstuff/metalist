# Enhanced Copy Functionality - HTML Export to System Clipboard

## Feature Overview
Enhance the Cmd+C functionality to copy the entire note hierarchy (including children) as HTML to the system clipboard when no text is selected, while maintaining the existing server-side clipboard functionality.

## Current Behavior
When pressing Cmd+C with no text selected:
1. Saves current note content to server
2. Adds note to server-side clipboard (for internal paste operations)
3. System clipboard is not used

## Desired Behavior
When pressing Cmd+C with no text selected:
1. Saves current note content to server (unchanged)
2. Adds note to server-side clipboard (unchanged)
3. **NEW**: Also copies the entire note hierarchy as HTML to system clipboard
   - Includes the selected note and all its children
   - Formatted as HTML that can be pasted into Gmail, Word, etc.
   - Preserves hierarchy structure visually

## Implementation Plan

### 1. Server-Side Changes
- Create new API endpoint: `/api/notes/{id}/export-html`
  - Returns the note and all children as formatted HTML
  - Includes proper indentation/nesting for hierarchy
  - Returns clean HTML suitable for external applications

### 2. Client-Side Changes
- Modify `handleCopyNoteShortcut` in `keyboard-events.js`:
  - After successful server clipboard copy
  - Fetch HTML version from new endpoint
  - Copy HTML to system clipboard using Clipboard API
  
### 3. HTML Format Structure
```html
<div class="metalist-note-export">
  <div class="note-content">Main note content here</div>
  <div class="note-children" style="margin-left: 20px;">
    <div class="note-content">Child 1 content</div>
    <div class="note-children" style="margin-left: 20px;">
      <div class="note-content">Grandchild content</div>
    </div>
    <div class="note-content">Child 2 content</div>
  </div>
</div>
```

### 4. Technical Considerations
- Use browser Clipboard API for writing HTML
- Fall back to execCommand('copy') if Clipboard API unavailable
- Ensure HTML is sanitized but preserves formatting
- Handle both plain text and HTML MIME types

### 5. Testing Requirements
- Test copying single notes without children
- Test copying notes with deep hierarchy
- Test pasting into various applications (Gmail, Word, etc.)
- Verify server-side clipboard still works for internal operations
- Test with various content types (lists, formatting, etc.)

## Success Criteria
- [ ] Cmd+C with no selection copies HTML to system clipboard
- [ ] HTML can be pasted into Gmail and renders correctly
- [ ] Hierarchy is visually preserved in pasted content
- [ ] Server-side clipboard functionality remains unchanged
- [ ] No regression in existing copy/paste behavior