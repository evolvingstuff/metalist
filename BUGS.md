# Known Bugs

## Comment Highlighting - Cursor Jump on Enter Key

**Status:** Fixed  
**Severity:** Medium  
**Date Discovered:** 2025-08-21  
**Date Fixed:** 2025-08-21  

### Description
When comment highlighting is enabled and the user presses Enter in the middle or at the end of a line, the cursor jumps to an incorrect position instead of staying on the new line. This makes editing with Enter key unusable when comment highlighting is active.

### Symptoms
1. When pressing Enter at the end of a line (e.g., after "1234"), cursor briefly appears on the new line then jumps back to the end of the previous line
2. When pressing Enter in the middle of text (e.g., between "thoma" and "s"), cursor ends up at the wrong position on the wrong line
3. The cursor briefly appears in the correct position (visible for ~1/10th second) before jumping to the wrong location

### Root Cause
The issue is in the comment highlighting cursor preservation logic in `/app/static/js/modules/comment-utils.js`:

1. When Enter creates a new block element (div), the cursor is placed in an empty div
2. `_getTextOffsetInElement()` fails to properly handle non-text nodes (empty divs) - it silently returns the total text length as a fallback
3. When `_setTextOffsetInElement()` tries to restore the cursor position, it interprets this offset as a position within the existing text, placing the cursor at the end of the previous line instead of in the new empty block

The fundamental problem is that the code uses a linear text offset model but contenteditable uses a hierarchical DOM structure with block elements. After Enter creates new blocks, the linear offset doesn't map correctly back to the DOM position.

### Temporary Fix
Comment highlighting has been disabled by commenting out the following lines:

1. `/app/static/js/modules/mode-manager/events/input-events.js` line 78:
   ```javascript
   // scheduleCommentHighlighting(noteContent);  // DISABLED - cursor bug with Enter key
   ```

2. `/app/static/js/modules/mode-manager/events/input-events.js` line 122:
   ```javascript
   // CommentUtils.highlightComments(noteContentElement);  // DISABLED - cursor bug with Enter key
   ```

### Permanent Fix Needed
The cursor position save/restore logic needs to be rewritten to:
1. Properly handle cursor positions in empty block elements (not just text nodes)
2. Never silently return fallback values - fail loudly when position cannot be determined
3. Consider using a different approach for cursor preservation that accounts for DOM structure, not just text offsets

### Related Files
- `/app/static/js/modules/comment-utils.js` - Contains the buggy cursor preservation logic
- `/app/static/js/modules/mode-manager/events/input-events.js` - Calls comment highlighting on input events

### Notes
- This bug only affects Enter key - regular typing works fine
- The highlighting itself works correctly, only cursor restoration is broken
- The bug was present from the initial implementation of comment highlighting (commit 60ba956)