# Search Query Syntax Verifier Plan

## Scope (This Feature)

Implement a **client-side search query syntax verifier + active rewrite**:
- Enforce a small grammar while typing (like the tag bar).
- Provide real-time warnings for incomplete syntax.
- Produce a normalized query string for storage/transport.

This feature **does not implement actual search semantics or filtering**.

Search does **not** execute while the query is syntactically incomplete.

## Term Model

Query is a whitespace-separated list of terms.

### Tag Terms

- `foo`
- `-foo`
- `+foo`

Notes:
- `+`/`-` semantics are out of scope; we only validate and parse.
- Tag tokens use the same character rules as tag-bar *non-wrapper* tokens.
- Bracket wrappers (`[foo]`, `{foo}`, `((foo))`) are **not** part of search syntax.

### Text Terms

A text term is a quoted string using either quote character, as long as it matches:

- Double-quoted: `"some text"`
- Single-quoted: `'some text'`
- Negated forms: `-"some text"`, `-'some text'`

Escapes inside quoted text (backslash approach):
- Within `"..."`: allow `\\` and `\"`
- Within `'...'`: allow `\\` and `\'`

How to search for quote characters without escaping:
- Search for a literal `"`: use single quotes: `'"'`
- Search for a literal `'`: use double quotes: `"'"`

## Validation + Completeness Rules

The verifier outputs:
- `normalizedText`: what we rewrite the input to while typing (whitespace normalization + enforcement).
- `sanitizedText`: only the *complete* terms.
- `isComplete`: `true` only when there are no incomplete terms.
- `warningMessage`: `null` or a user-facing string.

Rules:
1. **Whitespace**: normalize runs of whitespace to a single space; trim ends.
2. **Unclosed quotes**: if a term starts a quote and doesn't close it, the query is **incomplete**.
   - Show a warning (e.g. `Close quote with "` or `Close quote with '`)
   - `isComplete=false` and search does not execute.
3. **Empty quoted strings**: `""` and `''` are treated as **incomplete**.
   - Show a warning (e.g. `Enter text inside quotes`)
   - `isComplete=false` and search does not execute.
4. **Dangling prefixes**: `-` alone or `+` alone are **incomplete**.
5. **Invalid tag token characters**: actively removed during enforcement (tag-bar-style).

## Not Supported

- Bracket wrappers (`[]`, `{}`, `()`): tag-bar-only.
- Comments (`/* ... */`): tag-bar-only.
- Regex / wildcard / operators beyond `+`/`-` prefixes.

## Implementation Plan (Client)

1. Add a new module mirroring the tag-bar patterns:
   - `enforceSearchQueryInputForEditing(rawInput)` → rewritten string
   - `analyzeSearchQueryInput(rawInput)` → `{ normalizedText, sanitizedText, isComplete, warningMessage, terms }`
   - `normalizeSearchQueryInput(rawInput)` → `normalizedText`

2. Wire enforcement into the search input handler:
   - On `input`: rewrite value + preserve selection (same approach as tag bar).
   - Update warning UI state based on `analyzeSearchQueryInput()`.
   - Ensure execution requests are gated on `isComplete`.

## Examples (Syntax Only)

| Query | Notes |
|-------|------|
| `foo bar` | 2 tag terms |
| `-foo +bar` | tag terms with prefixes |
| `"hello world"` | double-quoted text term |
| `'hello world'` | single-quoted text term |
| `'"'` | literal double-quote character |
| `"'"` | literal single-quote character |
| `"say \"hi\""` | escaped quotes inside `"..."` |
| `'say \'hi\''` | escaped quotes inside `'...'` |

## Edge Cases

- Empty / whitespace-only query: complete and valid.
- `"unclosed`: warning, `isComplete=false`.
- `'unclosed`: warning, `isComplete=false`.
- `""` or `''`: warning, `isComplete=false`.
- `-` or `+` alone: warning, `isComplete=false`.
