# Note Content Formatting (Meta Tags)

## Overview
- Note content is stored as HTML (`notes.content`).
- The server can apply **view-only** formatting transformations based on **meta tags** (tags starting with `@`) in the tag bar (`notes.tags`).
- **Editing vs viewing:**
  - When a note is being edited by the current client, the server sends **raw content** so all delimiters remain visible.
  - Otherwise the server sends **rendered view HTML**, which may consume delimiters and wrap regions in styling spans.
  - Embedded note references use `![[UUID]]` and are rendered only in view mode.

## Embedded Note References
- Syntax: `![[UUID]]`
- In **view mode**, the token renders as an embedded note block:
  - It always renders as a block on its own visual line, even when written inline (for example `blah ![[UUID]] yada`).
  - The referenced note's full child subtree is rendered inside the embed.
  - Embedded rendering ignores the referenced note's collapsed/expanded state.
  - Missing UUIDs render a "missing reference" marker.
  - Circular reference chains render a "circular reference" marker and stop at that point.
- In **edit mode**, the token remains literal text (`![[UUID]]`).
- Full reference behavior and shortcut workflow: `docs/ui/references.md`.

## Links In View Mode
- Bare `http://...` and `https://...` text in rendered note content is auto-linked in view mode.
- Existing rendered anchors are normalized to open in a new browser tab.
- Internal hash-style anchors used by MetaList note-reference UI are left unchanged so in-app reference navigation still works.

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

## Email meta tags
- `@email`: renders the note content as an email row (envelope icon + "Email:") in view mode.
- Clicking the value opens the system email client (`mailto:`).

## Status meta tags
- `@todo`: renders the note content with an unchecked box icon in view mode; clicking the icon toggles the tag to `@done`.
- `@done`: renders the note content with a checked box icon in view mode; clicking the icon toggles the tag to `@todo`.

## Markdown meta tags
- `@markdown`: renders the note content as Markdown in view mode on the server.
- Collapsed notes still render a one-line preview; oversized heading styles are normalized in that preview so the first line remains visible and thumbnail behavior for images is preserved.
- For collapsed previews where the first visible content includes an image, the image thumbnail is intentionally larger (about 3x the baseline collapsed height) to keep image context readable.

## LaTeX meta tags
- `@LaTeX`: renders the note content as LaTeX in view mode (using KaTeX in the browser).
- Invalid LaTeX shows a red "Invalid LaTeX" badge and the raw content.
- Inline math uses `$...$`; display math uses `$$...$$`.
- If no `$` delimiters are present, the entire note is rendered as display math.

## Shell meta tags
- `@shell`: renders the note content as a terminal-style script block in view mode.
- Clicking the block starts a background shell session on the connected server and streams stdout/stderr inline while it runs.
- Running sessions accept stdin from an inline input box, so prompts like `read`, `input()`, or password confirmations can be answered without leaving the note.
- The transport is cross-platform (Windows/macOS/Linux), but the script itself still runs inside the server host's shell, so command syntax must match that host environment.

## JSON meta tags
- `@json`: parses the note content as JSON and pretty-prints it in view mode.
- Invalid JSON shows a red "Invalid JSON" badge and the raw content.

## CSV meta tags
- `@csv`: parses the note content as CSV and renders it as a table in view mode.
- Invalid CSV shows a red "Invalid CSV" badge and the raw content.
- Scoped wrappers (e.g. `((@csv))`) render only the wrapped region as a CSV table.
