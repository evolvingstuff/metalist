# PLAN.toolbar

## Context
- Toolbar started as TipTap experiment but we abandoned it because its event and selection model clashed with our live note editor.
- Current approach: fully custom toolbar targeting `contenteditable` note bodies, selection tracking via `editor-selection.js`, and toolbar bindings in `editor-toolbar.js` + `editor-commands.js`.
- Inline formatting (bold, italic, underline, inline code) now bypasses `document.execCommand` and uses a shared `toggleInlineElement(tagName)` helper that wraps/unwraps the range manually, then re-selects it. This works reliably because we own the DOM mutations.

## What Works Today
1. **Selection tracking**
   - `editor-selection.js` persists the active editable, note ID, and the last known `Range`.
   - Toolbar clicks call `withSelection`, which restores the saved range and re-focuses the editable before executing any command, then snapshots the range afterward.
2. **Inline commands**
   - Bold/Italic/Underline/Inline Code share the same flow: extract contents of the current range, wrap them in the correct semantic tag (`strong`, `em`, `u`, `code`), or unwrap the existing tag if already applied.
   - Because we directly manipulate the DOM and reapply the identical `Range`, the selection is preserved across repeated toggles.
3. **Toolbar button state**
   - `editor-toolbar.js` queries the DOM (for inline code) or legacy `execCommand` state (bold/italic/underline—soon to be removed) plus block-level detection to reflect button activation.

## Problems Encountered with Block-Level Ops
1. **`document.execCommand` selection collapse**
   - Block commands (headings, blockquote, ordered/unordered lists) still depend on `execCommand`.
   - We tried inserting hidden `<span data-selection-marker="start|end">` markers before running the command, then rebuilding the `Range` from those markers afterward. This works momentarily, but browsers emit additional asynchronous `selectionchange` events that collapse the caret back to the block start, overriding our restoration as soon as the markers are removed.
2. **Inconsistent toggling semantics**
   - We must detect the current block (`P`, `H1`, `BLOCKQUOTE`, etc.) before calling `execCommand` to emulate “toggle” behavior. Without this, repeated clicks just reapply the same style indefinitely.
3. **List normalization issues**
   - `execCommand('insertUnorderedList')` and `'insertOrderedList'` can generate nested `<div>` wrappers, merge adjacent lists unexpectedly, and produce inconsistent markup across browsers.
4. **Undo/redo opacity**
   - Because the browser is mutating the DOM internally, it’s hard to reason about what changed. This complicates syncing with our `ModeContext` dirty tracking and risks mismatches with the persisted HTML.
5. **Selection restoration race conditions**
   - Attempts to preserve selection with zero-width text nodes or span markers work momentarily, but the final browser-driven selection update still wins unless we hack around `selectionchange` globally, which is brittle.

## Direction: Custom Block Formatting Engine
Goal: treat every toolbar action—inline or block—as our own DOM transform layer so selections stay deterministic and markup stays predictable.

### Principles
- **Own the DOM mutations**: Do not rely on `execCommand`. Implement transformation helpers per format (inline code already proves the pattern).
- **Operate on explicit ranges**: Use the saved `Range` to identify affected nodes, transform them, then rebuild the exact same `Range` post-mutation.
- **Normalize structure**: Enforce consistent markup (e.g., block-level wrappers should always be `p`, `blockquote`, `h1-h3`, `ul/ol > li`). Strip browser-inserted spans/divs.
- **Mirror toggles**: Each helper should accept a `Range` and return whether it wrapped or unwrapped, so toolbar state can stay in sync without querying the browser.
- **Centralize selection preservation**: Provide a reusable utility that, given the active editable + logical selection, applies a transformation callback and guarantees the same logical start/end offsets afterward.

### Proposed Building Blocks
1. **Range normalizer**
   - Expand the selection to whole block boundaries when necessary (e.g., to convert multiple paragraphs to a list).
   - Split text nodes at range edges to avoid partial node handling.
2. **Block wrapper helpers**
   - `wrapBlocks(range, tagName)`: wrap each block in the given tag, merging adjacent wrappers when possible.
   - `unwrapBlocks(range, predicate)`: remove wrapper tags and normalize back to paragraphs.
3. **List toggles**
   - Convert selected blocks into `<ul>`/`<ol>` with individual `<li>` children.
   - When toggling off, unwrap to `<p>` while keeping inline formatting intact.
   - Handle nested toggles (e.g., converting an existing `<ol>` to `<ul>`).
4. **Heading toggles**
   - Promote/demote block tags based on current state (e.g., `p` → `h2`, `h2` → `p`).
5. **Blockquote toggle**
   - Wrap contiguous blocks in `<blockquote>`, unwrap when already quoted.
6. **Inline formatting consolidation**
   - Keep `toggleInlineElement` but make it part of the same module that handles block transforms so the entire toolbar uses one abstraction (e.g., `applyInlineFormat(range, 'strong')`).
7. **Selection persistence**
   - Instead of DOM markers, compute logical offsets relative to the editable (e.g., path + offset) before the transform and recreate the `Range` afterward. Node-splitting helpers should return handles for rebuilding the range precisely.

### Implementation Sketch
1. **Refactor structure**
   - Create `editor-formatting.js` with shared helpers: node splitting, block enumeration, list manipulation, selection rebuild.
   - `editor-commands.js` becomes thin wrappers that call these helpers based on toolbar buttons.
2. **Step-by-step transformation pipeline**
   - `captureSelectionSnapshot()` returns a data structure describing the start/end containers + offsets relative to block boundaries.
   - Formatting helper performs DOM edits (wrap, unwrap, convert lists) and returns updated anchors.
   - Rebuild the `Range` using anchors and update `savedRange`.
3. **Testing/verification**
   - Manual scenarios: toggling each block type on/off, converting multiple paragraphs at once, nested list conversions, interacting with inline formatting within block transformations.
   - Future automated tests (e.g., playwright) could validate HTML output + selection invariants.

## Open Questions / Risks
- **Undo/Redo integration**: Need to ensure manual DOM edits continue to synchronize with ModeContext dirty tracking and any future undo stack.
- **Cross-browser quirks**: Custom logic must handle Safari, Chrome, and Firefox contentEditable differences (e.g., how they split text nodes or treat empty blocks).
- **Performance**: Large selections might involve many DOM operations; we should benchmark and optimize (e.g., batching mutations, minimizing reflows).
- **Accessibility**: Ensure wrapper changes preserve semantic meaning and ARIA considerations.

## Next Steps
1. Design the selection-anchor abstraction (likely path-based) so we can rebuild ranges without relying on DOM markers.
2. Implement list toggle helper first (most complex), then reuse patterns for blockquote and headings.
3. Fold existing inline helper into the new formatting module for a consistent API.
4. Update toolbar state detection to rely on our DOM inspection rather than `document.queryCommandState`.
5. Document the expected HTML structure and add linting/validation to catch unexpected nodes early.
