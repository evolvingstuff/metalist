# Tag Bar

## Overview
- Each note has a tag string (`notes.tags`) that round-trips through the view snapshot (`snapshot.notes[*].tags`).
- The tag bar editor enforces a small grammar in the browser so invalid characters/sequences are removed as you type.
- When leaving the tag bar (Tab toggle or click-away) the input is **sanitized**: incomplete/broken items are removed.

## Whitespace + Tokens
- Outside of `/* ... */` comments, tags are separated by whitespace.
- Runs of whitespace are normalized to single spaces.
- Wrapper tokens may contain internal spaces (e.g. `{{@red @monospace}}`), which are preserved (normalized) inside the wrapper. This means a wrapper token can contain multiple tags.
- A normal tag token allows only ASCII-printable characters and disallows: `: " \\ > < = [ ] { } ( ) * | ; ~ ``.
- Tag tokens also cannot start with `-`, `+`, or `/`.

## Wrapper Tags
A tag token may be wrapped with matching brackets:
- `[]`, `{}`, or `()`
- Repeat count: **1–3**, and the opener/closer must match.

Examples (legal):
- `[tag]`
- `((tag))`
- `{{{tag}}}`

Examples (autocorrected while typing):
- `[tag)` → `[tag`
- `((tag))}` → `((tag))`

## Meta Tags (Formatting)
- Tags starting with `@` are reserved for server-side behaviors.
- Global meta tags apply to the whole note when unwrapped (e.g. `@red`).
- Scoped meta tags apply only to regions of note content wrapped with the same bracket type + depth.
  - Example: tag bar `{{@monospace}}` applies monospace styling to `{{...}}` regions in the note.
  - Depth must match exactly: `[[...]]` matches `[[@tag]]`, not `[@tag]` or `[[[@tag]]]`.
- Basic formatting tags:
  - `@heading` increases font size and weight.
  - `@bold`, `@italic`, `@strikethrough` apply basic text styling.
  - `@serif` switches to a serif font.
  - `@red`, `@green`, `@blue`, `@grey` apply text colors.
  - `@copyable` makes the rendered content clickable to copy its raw text to the clipboard.
  - `@dark-theme` renders the content with a dark background + light text.
  - Ontology implication rules can add these formatting tags implicitly (e.g. `bug => @red`).
- List meta tags:
  - `@list-bulleted` renders the note's immediate children with bullet markers.
  - `@list-numbered` renders the note's immediate children with numbered markers.
  - Only the **direct** children are affected (grandchildren are not).
- Credential meta tags:
  - `@username` renders a view-only "Username:" row with a copyable value.
  - `@password` renders a view-only "Password:" row with a blurred, copyable value.
- Email meta tags:
  - `@email` renders a view-only "Email:" row with a mailto link.
- Status meta tags:
  - `@todo` renders an unchecked box icon; clicking the icon toggles the tag to `@done`.
  - `@done` renders a checked box icon; clicking the icon toggles the tag to `@todo`.
- Markdown meta tags:
  - `@markdown` renders note content as Markdown in view mode.
- LaTeX meta tags:
  - `@LaTeX` renders note content as LaTeX in view mode (KaTeX).
  - Use `$...$` for inline math and `$$...$$` for display math.
  - If no `$` delimiters are present, the entire note is rendered as display math.
  - Scoped LaTeX works with wrappers (e.g. `{{@LaTeX}}` renders only `{{...}}` segments) and can be combined with `@markdown` to render math inside Markdown.
- Shell meta tags:
  - `@shell` renders note content as a terminal-style script block in view mode.
  - Clicking the block starts a background shell session on the server and updates stdout/stderr inline while the command is still running.
  - A running shell session can accept stdin from an inline input field.
  - The transport is cross-platform, but note scripts still need to match the connected server host's shell and OS conventions.
- JSON meta tags:
  - `@json` pretty-prints note content as JSON; invalid JSON shows an error badge and raw text.
- CSV meta tags:
  - `@csv` renders note content as a CSV table; invalid CSV shows an error badge and raw text.
  - `((@csv))` renders only the wrapped content as a CSV table.

Wrapper regions in note content are always allowed (e.g. `((foo))`), but they are only consumed/hidden in view mode when there is a matching scoped wrapper tag in the tag bar (meta tags like `{{@red}}` or regular tags like `{{foo}}`). Otherwise the wrappers remain literal text.

Wrapper tokens can contain multiple tags separated by spaces (e.g. `{{@red @monospace}}`).

Notes:
- Multiple tags inside a wrapper are still stored as a single wrapper token in the tag bar (i.e., the internal whitespace does not “split” it into separate top-level tokens).
- Non-meta tags inside wrapper tokens are allowed (e.g. `{{foo bar}}`) for future semantic uses; currently only `@...` meta tags affect formatting.

If a wrapper is opened but not closed:
- It does not immediately warn on a bare opener like `(`.
- Once there is content (e.g. `(tag`), the tag bar shows a warning and the incomplete token is omitted from the saved tag string.
- When you leave the tag bar, the incomplete token is removed from the input.

## Comments
You can include `/* ... */` comment segments in the tag bar:
- Comments may contain spaces.
- Comment text is preserved (ASCII-printable characters only).

Comments also participate in server-side text search.

Unclosed comments behave like unclosed wrappers:
- A bare `/*` does not immediately warn.
- Once there is content (e.g. `/*comment`), the tag bar warns.
- Unclosed comments are omitted from the saved tag string and are removed when leaving the tag bar.

## Tag Suggestions
- Suggestions appear only while the tag bar input is focused.
- While typing inside a tag token, matching is segment-aware for connector-separated tags: a prefix can match the start of the whole tag or the start of any connector-separated segment (`-`, `_`, `.`, `/`). Example: `wor` suggests both `workspaces` and `databricks-workspaces`, while `orksp` suggests neither.
- When the active prefix starts with `@`, matching meta tags are ranked by notebook usage frequency (note count), with alphabetical tiebreaks for equal counts.
- After a space, suggestions are ranked by tag co-occurrence.
- Tags that match phrases in the note content are listed first.
- A literal content hit on any connector-separated segment can also surface a tag. Full multi-segment phrase hits rank above single-segment hits, so content like `databricks workspaces` prefers `databricks-workspaces` over either segment tag alone.
- When content-hit strength ties, earlier mentions in the note rank ahead of later mentions.
- Surrounding prose punctuation is ignored for content matching, so content like `(github?)` still promotes the `github` tag.
- Case-equivalent tags are collapsed in suggestions (for example `Databricks` vs `databricks`), and the most-used spelling is shown.
- Tags already present explicitly in the current tag bar are never suggested.
- Tags already present only via inheritance or ontology inference are suppressed unless they match the prefix (then they appear at the bottom).
- Suggestions appear below the tag bar when there is room; if the tag bar is near the bottom, the list flips upward and the ordering reverses so the closest suggestion sits nearest the input.
- The connector characters used for content matching are configurable via `TAG_SUGGESTION_CONNECTORS` in `app/config.py`.

## Focus / Tab Behavior
- `Tab` toggles focus between the note content and the tag bar.
- When leaving the tag bar (Tab or click-away), the tag string is sanitized so only valid, fully-formed tokens/comments remain.
- While the single-note tag bar is focused, note-level edit shortcuts still target the current note, including create sibling/child, delete, move up/down, indent/outdent, join, split, note copy/cut/paste, and the password modal shortcut.
- `Cmd/Ctrl+J` join-note merges tag bars and dedupes repeated tokens case-insensitively, preserving first occurrence order/casing.
