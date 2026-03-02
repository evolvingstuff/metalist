# Note References

## Status
- Implemented reference syntaxes:
  - `![[UUID]]` = embedded mode
  - `[[UUID]]` = link mode

## Rendering Rules
- **View mode**:
  - `![[UUID]]` renders the referenced note as an embedded block (with descendants).
  - `[[UUID]]` renders a compact link-style block showing only the referenced note's first line.
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

## Failure / Safety Cases
- Missing or deleted UUID: render a "missing reference" marker (subtly red-tinted).
  - Missing references do not show the `+/-` toggle control.
- Circular chain (A -> B -> A): render a "circular reference" marker and stop recursion at that point.

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
- `docs/ui/controls.md`
- `docs/ui/search-semantics.md`
- `docs/design/differential-view-protocol.md`
