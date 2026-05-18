# UUID References

## Status
- Implemented reference syntaxes:
  - `![[UUID]]` = embedded mode
  - `[[UUID]]` = link mode
- If the note has a matching `[[...]]` scoped wrapper tag (for example `[[@LaTeX]]`), `[[...]]` is parsed as content formatting instead of link mode. Use `![[UUID]]` for embedded references in that case, or use a different formatting wrapper delimiter.
- A UUID can resolve to either:
  - a note
  - a file attachment

## Rendering Rules
- **View mode**:
  - Note targets:
    - `![[UUID]]` renders the referenced note as an embedded block (with descendants).
    - `[[UUID]]` renders a compact link-style block showing only the referenced note's first line.
    - when the host note is collapsed, link-mode note references stay visible as a single compact row showing the preview text.
  - File targets:
    - non-image files render a file card/link row with a deterministic type badge (`PDF`, `IMG`, `VID`, `TXT`, etc.) and the file title.
    - embedded image files (`![[UUID]]`) render an authenticated image preview with a `download image` control beneath it.
    - right-clicking the rendered image preview also offers image actions (`Copy Image`, `Save Image`, `Zoom Image`, `Open Image in New Tab`).
    - link-mode image files (`[[UUID]]`) keep the generic compact file card/link row.
    - clicking the rendered file reference downloads the decrypted file from the server.
    - when the host note is collapsed, non-image file references stay visible as a single compact row showing the badge and a truncated title.
    - when the host note is collapsed and the first visible line is an embedded image file, the note collapses to a compact thumbnail-only version of that image preview.
  - Each rendered reference has a `+/-` toggle:
    - `-` switches embed -> link.
    - `+` switches link -> embed.
  - Toggle actions mutate the raw token in note content (`![[...]]` <-> `[[...]]`) and work per-token occurrence.
  - The embed always renders on its own visual line (block), even when written inline.
  - The referenced note's child subtree is included.
  - Embedded rendering ignores collapsed/expanded state of the source note and renders fully expanded.
  - Embed blocks do not show normal note collapse arrows/affordances.
  - Clicking a link-mode reference opens UUID search for that note (it does not enter edit mode on the target note).
- **Edit mode**:
  - Tokens remain literal raw text (`![[UUID]]` or `[[UUID]]`).
  - Saved-file image actions are not available from the raw token; they are available once the token renders as an image preview in view mode.

## File Attachment Workflow
- `Attach file…` in the command palette opens the native file picker.
- If you are editing a note, the selected file is uploaded and its `![[UUID]]` token is inserted into that note.
- If no note is active, the app creates a new note first, then inserts the file reference there.
- Drag/drop follows the same attachment path for non-image files.
  - Dropping onto the actively edited note inserts into that note.
  - Dropping anywhere else creates a new top note first, then inserts there.
- Named image files dropped or pasted into the editor prompt for one of two paths:
  - `Paste Inline`: embed the image into note HTML as compressed `data:image/...`.
  - `Save as File`: upload the original file without recompression and insert its `![[UUID]]` token.
- Clipboard image-pixel paste with no meaningful source filename keeps the direct inline embed path by default.
- The attach flow saves the note immediately after insertion so the new reference survives refresh/reload.
- Files live in a sibling SQLite database derived from the main DB path (`*.files.db`).
- Startup only loads the file UUID registry into memory; file metadata/blob rows are decrypted on demand for rendering/download.

## Failure / Safety Cases
- Missing or deleted UUID: render a "missing reference" marker (subtly red-tinted).
  - Missing references do not show the `+/-` toggle control.
- Circular chain (A -> B -> A): render a "circular reference" marker and stop recursion at that point.
- Removing every note reference to a file does not delete the file automatically.
- `Trim unused files` is the explicit cleanup path for unreferenced file rows.

## Keyboard Workflow
- `Cmd/Ctrl + C` with no text selection copies a note (server clipboard + system clipboard payload).
- `Cmd/Ctrl + R` while editing copies as embedded reference (`![[UUID]]`) using the most recently copied note UUID.
- Insert behavior:
  - The token is inserted on its own line.
  - If caret is in the middle of a line, the line is split around the inserted reference.

## Search Semantics
- Embedded references are a **view transform**, not a search expansion.
- Referenced note tags do **not** affect search matching for the host note (neither positive nor negative).
- Host note search behavior continues to use host note content/tags plus existing inheritance/ontology rules.
- UUID link-click behavior:
  - Search input is set to the referenced UUID.
  - Target note is included.
  - Target ancestors are included.
  - Target descendants are included (not redacted).
  - Non-matching sibling branches in visible context are redacted via normal search rules.

## Related Docs
- `docs/ui/content-formatting.md`
- `docs/ui/command-palette.md`
- `docs/ui/controls.md`
- `docs/ui/search-semantics.md`
- `docs/design/differential-view-protocol.md`
