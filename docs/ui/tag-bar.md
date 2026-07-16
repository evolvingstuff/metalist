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
  - `@todo` renders an unchecked box icon; pressing the icon toggles the tag to `@done` on mouse down.
  - `@done` renders a checked box icon; pressing the icon toggles the tag to `@todo` on mouse down.
  - If another note is being edited, pressing a status icon saves and exits that edit session before toggling, without selecting the toggled note for editing.
- Image meta tag:
  - `@image` is inferred dynamically for search when note content contains inline image markup, a Markdown image link, or an embedded file reference whose attachment metadata is an image.
  - The tag is search-only; it is not persisted in the note's tag bar and does not change note rendering.
- Markdown meta tags:
  - `@markdown` renders note content as Markdown on the server in view mode.
- LaTeX meta tags:
  - `@LaTeX` renders note content as LaTeX on the server in view mode.
  - The server emits final MathML directly; the browser does not finish a second LaTeX rendering pass.
  - Use `$...$` for inline math and `$$...$$` for display math.
  - If no `$` delimiters are present, the entire note is rendered as display math.
  - Scoped LaTeX works with wrappers (e.g. `{{@LaTeX}}` renders only `{{...}}` segments) and can be combined with `@markdown` to render math inside Markdown.
- Shell meta tags:
  - `@shell` renders note content as a terminal-style script block in view mode.
  - Clicking the block starts a background shell session on the server and updates stdout/stderr inline while the command is still running.
  - Completed/error/timeout shell feedback can be dismissed with the inline `Close` button in the output header.
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
- The active typed prefix and note content provide complementary literal evidence. Once a prefix identifies a connector-separated segment, the remaining tag segments are matched against the note, so typing `GPT` in content containing `5.6 sol` promotes `GPT-5.6-sol` over more frequently used `GPT-*` tags.
- When the active prefix starts with `@`, matching meta tags are ranked by notebook usage frequency (note count), with alphabetical tiebreaks for equal counts.
- Tags that match phrases in the current note content and the strongest direct co-occurrence hits from the current note's explicit non-meta tags share the top slots together: the strongest content hit appears first, then the strongest co-occurrence hit, then the next content hit, and so on.
- For blank-prefix suggestions only, if a candidate's literal content match is driven entirely by segments that are already represented in an explicit or inherited tag on the note, that candidate is suppressed as redundant. Example: with `fat.appearance` already present, content-only matches like `fat-loss` or `body-fat` do not crowd out unrelated co-occurrence suggestions such as `overindulging`.
- After that, suggestions are boosted by nearby hierarchy context: explicit tags and literal content matches from the current note's descendants, nearby sibling subtree, and ancestor note content.
- Remaining suggestions fall back to other notes whose effective context overlaps the current note's explicit/inherited/inferred non-meta tags, but the emitted non-meta suggestions still come only from explicit tags assigned on those notes.
- A literal content hit on any connector-separated segment can also surface a tag, but low-signal glue segments like `and`, `no`, `of`, `the`, `to`, or `up` do not count on their own. They still participate in exact full-phrase literal matches, so content like `No Kings` can strongly promote `no-kings` even though bare `no` would not.
- Connector-heavy tags need near-complete literal coverage before they surface from content alone: if a tag has `k` raw connector-separated chunks, content must cover at least `k-1` of those chunks, capped by the number of meaningful non-noise chunks in the tag. That means `X-Y-Z` can surface for `X Y`, `Y Z`, or `Y X`, but not for `X`, `Y`, `Z`, or an unrelated two-chunk overlap like `W Z`.
- Numeric chunks remain insufficient on their own, but they count inside a contiguous near-complete connector phrase that also contains a meaningful text chunk. For example, content `5.6 sol` can promote `GPT-5.6-sol`, while content `5.6` alone does not promote `GPT-5.6`.
- When content matches only part of a connector-separated tag, the most literal candidate wins first: fewer unmatched connector segments rank ahead of more padded tags, and prefix-aligned partials beat suffix-aligned ones when coverage otherwise ties. Examples: `Z` prefers `Z` over `Y-Z`, `Y` prefers `Y-Z` over `X-Y`, and `Y Z` prefers `Y-Z` over `Z` over `X-Y-Z`.
- Single-character connector segments are still ignored for lowercase noise like `a-b-test`. Uppercase one-letter segments can still count as meaningful literals for entity-like tags, but prose-like `A` and `I` are treated as noise so they do not boost unrelated suggestions.
- When content-hit strength ties, more structured/specific tags rank ahead of broader/common ones. Mixed-case tags, digit-bearing tags, connector-separated tags, and prefix-aligned segment matches beat looser matches; usage frequency then breaks ties before raw tag length or alphabetical ordering.
- Surrounding prose punctuation is ignored for content matching, so content like `(github?)` still promotes the `github` tag.
- Case-equivalent tags are collapsed in suggestions (for example `Databricks` vs `databricks`), and the most-used spelling is shown.
- Ontology-equivalent tags are usually collapsed to one displayed suggestion. The representative is the most-used eligible tag spelling explicitly written in tag bars, not the ontology-inferred search frequency, but prefix filtering happens first, so typing `emo` can still show `emotion` even if `mood` is the more common synonym overall. If the current note content exactly matches a synonym alias, that alias can still appear immediately after the common representative within the interleaved content/co-occurrence ordering.
- Tags declared in ontology rules remain eligible for literal-content matching and typed-prefix completion even when they have never been explicitly assigned to a note. With a blank prefix, unrelated unused ontology tags are not added as generic fallback suggestions.
- Tags already present explicitly in the current tag bar are never suggested.
- Tags already present only via inheritance or ontology inference are suppressed unless they match the prefix (then they appear at the bottom).
- Suggestions appear below the tag bar when there is room; if the tag bar is near the bottom, the list flips upward but keeps the same best-on-top ordering and initial scroll position.
- The server returns at most `MAX_TAG_SUGGESTIONS` note tag suggestions; the default is 20.
- The connector characters used for content matching are configurable via `TAG_SUGGESTION_CONNECTORS` in `app/config.py`.
- The redundant-content suppression rule is configurable via `TAG_SUGGESTION_SUPPRESS_REDUNDANT_CONTENT_VARIANTS` in `app/config.py`.

## Focus / Tab Behavior
- `Tab` toggles focus between the note content and the tag bar.
- Clicking the visible tag bar while editing focuses the tag input directly instead of treating the click as a note-shell selection.
- The tag bar expands into view when note editing starts and contracts out of view when editing ends, unless `Animated transitions` is off in the command palette.
- When leaving the tag bar (Tab or click-away), the tag string is sanitized so only valid, fully-formed tokens/comments remain.
- While the single-note tag bar is focused, note-level edit shortcuts still target the current note, including create sibling/child, delete, move up/down, move to top, indent/outdent, split, unformat, note copy/cut/paste, and the password modal shortcut.
- `Cmd/Ctrl+U` unformats the note content while preserving links, images, and the tag bar itself.
