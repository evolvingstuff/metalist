# Search Syntax

## Scope
- This document describes the **client-side search query syntax verifier**.
- It does **not** describe search semantics (what matches what).
- Search execution is gated by syntactic completeness: incomplete queries do not execute.

## Terms
Search queries are a whitespace-separated list of **terms**.

### Tag Terms
- `foo`
- `-foo`
- `+foo`

Notes:
- `+`/`-` semantics are out of scope here; they are just syntactic prefixes.
- Tag tokens follow the same character rules as tag-bar *non-wrapper* tokens.
- Bracket wrappers (`[foo]`, `{foo}`, `((foo))`) are **not** part of search syntax.

### Text Terms
A text term is a quoted string using either quote character, as long as the opener and closer match:
- Double-quoted: `"some text"`
- Single-quoted: `'some text'`
- Negated forms: `-"some text"`, `-'some text'`

Escapes inside quoted text (backslash approach):
- Within `"..."`: allow `\\` and `\"`
- Within `'...'`: allow `\\` and `\'`

Searching for quote characters without escaping:
- Search for a literal `"`: use single quotes: `'"'`
- Search for a literal `'`: use double quotes: `"'"`

## Normalization
- Runs of whitespace are normalized to single spaces.
- Leading/trailing whitespace is trimmed.
- The verifier actively rewrites the input while typing (cursor/selection is preserved).

## Completeness + Warnings
The verifier produces:
- `normalizedText`: the normalized query string.
- `sanitizedText`: only complete terms.
- `isComplete`: whether the full query is syntactically complete.
- `warningMessage`: user-facing warning text (or `null`).

Rules:
- **Unclosed quotes**: incomplete. Warn once there is content inside the quote.
  - Example: `"unclosed` → warn `Close quote with "`
- **Empty quoted strings**: incomplete and warned.
  - Examples: `""` and `''` → warn `Enter text inside quotes`
- **Dangling prefixes**: `+` or `-` alone is incomplete, but does not immediately warn.

## Implementation
- Verifier: `app/static/js/modules/mode-manager/services/search-syntax-service.js`
- Input enforcement + warning rendering: `app/static/js/modules/mode-manager/services/search-input-service.js`

