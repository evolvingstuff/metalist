# Note Content Formatting (Meta Tags)

## Overview
- Note content is stored as HTML (`notes.content`).
- The server can apply **view-only** formatting transformations based on **meta tags** (tags starting with `@`) in the tag bar (`notes.tags`).
- **Editing vs viewing:**
  - When a note is being edited by the current client, the server sends **raw content** so all delimiters remain visible.
  - Otherwise the server sends **rendered view HTML**, which may consume delimiters and wrap regions in styling spans.

## Content Wrappers
- Wrappers in note content are semantic markup regions:
  - `{{...}}`, `[[...]]`, `((...))`
  - Depth 1–3 is supported (e.g. `{{{...}}}`).
- Wrappers in content are **only consumed/hidden** in view mode when there is a matching *scoped wrapper tag* in the tag bar.
- If there is **no matching scoped wrapper tag**, wrappers are treated as literal text and remain visible even out of edit mode.

Scoped wrapper tags do not need to be meta tags:
- Example: tag bar `[foo]` causes all `[...]` regions in the note to render without the brackets in view mode.

## Meta Tags

### Global meta tags
- A meta tag with no wrapper applies to the entire note content.
- Example: `@red` makes the whole note red.

### Scoped meta tags
- A wrapped meta tag applies only to content wrapped with the same bracket **type** and **depth**.
- Examples:
  - Tag bar: `{{@monospace}}` → applies to `{{...}}` regions.
  - Tag bar: `[[[@red]]]` → applies to `[[[...]]]` regions.
- Depth must match exactly:
  - `[[...]]` matches `[[@tag]]`
  - `[[...]]` does **not** match `[@tag]` or `[[[@tag]]]`

Multiple tags can appear inside the same wrapper token (space-separated), and all recognized meta tags apply:
- Example: `{{@red @monospace}}`

### Nesting
- Scoped regions can be nested within each other.
- If the tag bar contains multiple scoped meta tags, the rendered view content may contain nested spans.

## Initial meta tags
- `@monospace`: renders the (scoped) region using a monospace/code font.
- `@red`: renders the (scoped) region in red.
