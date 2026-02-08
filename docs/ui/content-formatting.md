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

Other (non-meta) tags may also appear inside wrapper tokens (e.g. `{{foo bar}}`). Those tags are currently inert for formatting, but the presence of the wrapper token still enables consuming the matching content delimiters in view mode.

### Nesting
- Scoped regions can be nested within each other.
- If the tag bar contains multiple scoped meta tags, the rendered view content may contain nested spans.

## Initial meta tags
- `@monospace`: renders the (scoped) region using a monospace/code font.
- `@red`: renders the (scoped) region in red.
## Basic formatting tags
- `@heading`: increases font size and weight.
- `@bold`: renders bold text.
- `@italic`: renders italic text.
- `@strikethrough`: renders struck-through text.
- `@serif`: renders with a serif font.
- `@green`: renders text in green.
- `@blue`: renders text in blue.
- `@grey`: renders text in grey.
- Ontology implication rules can add these formatting tags implicitly (e.g. `bug => @red`).

## List meta tags
- `@list-bulleted`: renders the note's immediate children as a bulleted list in view mode.
- `@list-numbered`: renders the note's immediate children as a numbered list in view mode.
- Only direct children are affected (grandchildren are not).

## Credential meta tags
- `@username`: renders the note content as a credential row (user icon + "Username:") in view mode; the value is click-to-copy.
- `@password`: renders the note content as a credential row (lock icon + "Password:") in view mode; the value is blurred and click-to-copy.
- These are view-only: in edit mode you see just the raw value.

## Status meta tags
- `@todo`: renders the note content with an unchecked box icon in view mode; clicking the icon toggles the tag to `@done`.
- `@done`: renders the note content with a checked box icon in view mode; clicking the icon toggles the tag to `@todo`.

## Markdown meta tags
- `@markdown`: renders the note content as Markdown in view mode (using markdown-it in the browser).

## LaTeX meta tags
- `@latex`: renders the note content as LaTeX in view mode (using KaTeX in the browser).
- Invalid LaTeX shows a red "Invalid LaTeX" badge and the raw content.
- Inline math uses `$...$`; display math uses `$$...$$`.

## JSON meta tags
- `@json`: parses the note content as JSON and pretty-prints it in view mode.
- Invalid JSON shows a red "Invalid JSON" badge and the raw content.

## CSV meta tags
- `@csv`: parses the note content as CSV and renders it as a table in view mode.
- Invalid CSV shows a red "Invalid CSV" badge and the raw content.
- Scoped wrappers (e.g. `((@csv))`) render only the wrapped region as a CSV table.
