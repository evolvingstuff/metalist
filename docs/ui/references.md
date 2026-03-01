# Note References

## Status
- Implemented reference syntax in this release: `![[UUID]]` (embedded note reference).
- Deferred: plain links `[[UUID]]` (without `!`).

## Rendering Rules
- **View mode**:
  - `![[UUID]]` renders the referenced note as an embedded block.
  - The embed always renders on its own visual line (block), even when written inline.
  - The referenced note's child subtree is included.
  - Embedded rendering ignores collapsed/expanded state of the source note and renders fully expanded.
  - Embed blocks do not show normal note collapse arrows/affordances.
- **Edit mode**:
  - The token remains literal text: `![[UUID]]`.

## Failure / Safety Cases
- Missing or deleted UUID: render a "missing reference" marker.
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

## Related Docs
- `docs/ui/content-formatting.md`
- `docs/ui/controls.md`
- `docs/ui/search-semantics.md`
- `docs/design/differential-view-protocol.md`
