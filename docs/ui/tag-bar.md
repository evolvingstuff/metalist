# Tag Bar

## Overview
- Each note has a tag string (`notes.tags`) that round-trips through the view snapshot (`snapshot.notes[*].tags`).
- The tag bar editor enforces a small grammar in the browser so invalid characters/sequences are removed as you type.
- When leaving the tag bar (Tab toggle or click-away) the input is **sanitized**: incomplete/broken items are removed.

## Whitespace + Tokens
- Outside of `/* ... */` comments, tags are separated by whitespace.
- Runs of whitespace are normalized to single spaces.
- Wrapper tokens may contain internal spaces (e.g. `{{@red @monospace}}`), which are preserved (normalized) inside the wrapper.
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

Wrapper regions in note content are always allowed (e.g. `((foo))`), but they are only consumed/hidden in view mode when there is a matching scoped wrapper tag in the tag bar (meta tags like `{{@red}}` or regular tags like `{{foo}}`). Otherwise the wrappers remain literal text.

Wrapper tokens can contain multiple tags separated by spaces (e.g. `{{@red @monospace}}`).

If a wrapper is opened but not closed:
- It does not immediately warn on a bare opener like `(`.
- Once there is content (e.g. `(tag`), the tag bar shows a warning and the incomplete token is omitted from the saved tag string.
- When you leave the tag bar, the incomplete token is removed from the input.

## Comments
You can include `/* ... */` comment segments in the tag bar:
- Comments may contain spaces.
- Comment text is preserved (ASCII-printable characters only).

Unclosed comments behave like unclosed wrappers:
- A bare `/*` does not immediately warn.
- Once there is content (e.g. `/*comment`), the tag bar warns.
- Unclosed comments are omitted from the saved tag string and are removed when leaving the tag bar.

## Focus / Tab Behavior
- `Tab` toggles focus between the note content and the tag bar.
- When leaving the tag bar (Tab or click-away), the tag string is sanitized so only valid, fully-formed tokens/comments remain.
