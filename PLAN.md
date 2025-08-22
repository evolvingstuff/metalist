# Smart Paste Detection Feature

## Problem
When a user copies a note (Cmd+C), it goes to both server clipboard and system clipboard. If they then copy something externally (e.g., an image from Google), the app doesn't know the system clipboard has changed. On Cmd+V, it may paste the old note instead of the new content.

## Solution
Add intelligent paste detection by inspecting clipboard contents at paste time.

## Implementation Plan

### 1. Add Paste Event Listener
- Add a `paste` event listener alongside the existing keydown handler
- This gives us access to clipboard contents at paste time

### 2. Inspect Clipboard Contents
When paste event fires, check the clipboard data:
- Extract HTML content from `event.clipboardData`
- Look for our signature: the `note-content` class

### 3. Smart Routing Logic
- **If HTML contains `class="note-content"`**: This is our note HTML from earlier
  - Prevent default paste behavior  
  - Call the server clipboard paste functions (preserves structure/hierarchy)
- **Otherwise**: External content (text, images, other HTML)
  - Allow default paste behavior
  - Let browser handle it naturally

### 4. Clean Up State Tracking
- Remove `clipboardMode` state variable (no longer needed)
- Remove related state management code
- Simplify the copy/paste flow

### 5. Update Copy Behavior  
- Keep current copy behavior (copies to both server and system)
- Ensure HTML includes `note-content` class naturally (already does)

## Benefits
- No new keyboard shortcuts to learn
- Works with images, text, and any external content
- Preserves note structure when appropriate
- No permission prompts needed (paste event provides access)

## Testing Scenarios
1. Copy note → Paste in app (should use server clipboard)
2. Copy note → Copy external text → Paste in app (should paste external text)  
3. Copy note → Copy image → Paste in app (should paste image)
4. Copy note → Paste in Gmail (should paste HTML correctly)
5. Copy text from note → Paste elsewhere (should work normally)