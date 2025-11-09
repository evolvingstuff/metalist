# PLAN: Rich Text Editing Toolbar (Custom Implementation)

## Goal
Give the existing note editor a robust formatting toolbar (bold, italic, underline, inline code, block quote, headers, bullet + numbered lists) that appears only in editing mode, keeps selections intact across toolbar clicks, and avoids TipTap.

## Constraints & Guardrails
- Keep current `contenteditable` DOM; no external editors.
- Fail fast: throw on impossible states (missing selection, invalid toolbar command, etc.).
- No git operations unless explicitly approved.
- Reuse ModeManager (actions/event handlers) and ModeContext for state + dirty tracking.

## Work Breakdown

### 1. Baseline the Current Editor Flow
- Map how ModeManager enters/exits editing, saves content, and stores cursor offsets.
- Identify where selection info lives today (`ModeContext.savedCursorOffset`, DOMUtils cursor helpers).
- Document existing CSS/HTML hooks for notes and where the toolbar can mount.

### 2. Toolbar Markup & Styling
- Add a floating toolbar container in `notes_list.html` (or a separate template partial) that will house buttons for each command.
- Style it in `app/static/css/main.css` so it anchors to bottom center, matches app look, and is hidden by default.
- Include aria attributes for accessibility (`role="toolbar"`, `aria-pressed` states on buttons).

### 3. Toolbar Controller Module
- Create `app/static/js/modules/editor-toolbar.js` (or similar) to:
  - Track visibility based on ModeContext `isEditing`.
  - Register button click handlers.
  - Keep buttons in sync with current selection state (e.g., highlight the bold button when selection is bold).
- Ensure toolbar interactions don’t propagate to global click handlers that exit edit mode (stop propagation where needed).

### 4. Selection Management Utilities
- Build helper functions to capture and restore the user’s selection (`Range` snapshots) without relying on global `window.getSelection()` state alone.
- When entering edit mode: store the initial selection/caret.
- Before each toolbar command: restore the saved range, run the transformation, then save the updated selection.

### 5. Formatting Command Implementations (execCommand-first)
For each feature (bold, italic, underline, inline code, block quote, headers h1–h3, unordered & ordered lists):
- Prefer `document.execCommand` to minimize DOM-manipulation bugs. Wrap each command in helper functions (`runInlineCommand('bold')`, `toggleBlock('blockquote')`, etc.) so we can swap implementations later.
- Handle cases where `execCommand` falls short (e.g., inline code) by post-processing the selection/range, but keep those contained inside the helper layer.
- Normalize output HTML if necessary (e.g., map `<b>` to `<strong>` post-execution) so ModeContext stores consistent content.
- Update ModeContext dirty state and current content after each mutation so autosave + undo flows stay coherent.

### 6. Integrate With ModeManager & Events
- When ModeContext switches to editing, mount/activate the toolbar and selection tracking.
- On exit (click outside, switching notes, deletion), teardown listeners and ensure toolbar hides immediately.
- Update mouse/input event handlers to ignore clicks inside the toolbar so editing mode isn’t inadvertently canceled.

### 7. Testing & Validation
- Manual test matrix:
  - Enter edit mode, apply each formatting option, ensure content updates and dirty flag toggles.
  - Toggle the same button twice to confirm removal works.
  - Apply formatting, then click outside note—toolbar hides and formatting persists after re-entering edit mode.
  - Switch between notes, ensuring selection offsets restore correctly and toolbar state resets.
  - Save and reload to verify formatted HTML renders as expected.
- Document remaining edge cases (e.g., overlapping formats) for future iterations.
