# Search Query Syntax Implementation Plan

## Overview

Implement a search query parser that validates and parses space-separated search terms. The parser should provide real-time feedback (warnings) for incomplete/invalid syntax, similar to how the tag bar handles unclosed comments or bracket wrappers.

Search does not execute while the query is syntactically incomplete.

## Term Types

### Tag Terms

- `foo` — matches notes with tag `foo`, including tags that imply `foo` or are synonyms
- `-foo` — excludes notes with tag `foo` (negation)
- `+foo` — strict match for exactly tag `foo`, no implication/synonym expansion

Tag tokens follow the same character rules as those in the tag bar.

### Text Terms

- `"some text"` — matches notes containing this literal text
- `-"some text"` — excludes notes containing this literal text
- Escaped quotes inside text: `"escaped \"quote\" here"`

## Validation Rules

1. **Unclosed quotes** — A quoted string without a closing quote (e.g., `"some text`) triggers a warning. The incomplete term is omitted from the executed search.

2. **Well-formed terms** — Each term must be one of:
   - A tag term: optional `-` or `+` prefix, followed by a valid tag token
   - A text term: optional `-` prefix, followed by a properly closed quoted string

3. **Whitespace** — Terms are separated by whitespace. Runs of whitespace are normalized to single spaces.

## Not Supported

- **Bracket wrappers** — `[]`, `{}`, `()` wrappers are tag-bar-only (for scoping format meta tags to content regions)
- **Wildcards** — Not needed; prefix matching is inherent to tag implication
- **Regex** — Cannot be efficiently implemented with bloom filters over large note sets

## Implementation Notes

- Text matching will use bloom filters for efficiency at scale (100k+ notes)
- Tag matching uses the existing tag index with implication/synonym support
- Parser should emit warnings in real-time as user types (like the tag bar)
- Incomplete queries should not execute; only syntactically complete queries run

## Examples

| Query | Meaning |
|-------|---------|
| `foo` | Notes with tag `foo` (or implying tags) |
| `foo bar` | Notes with both `foo` and `bar` |
| `-foo` | Notes without tag `foo` |
| `+foo` | Notes with exactly tag `foo` |
| `"hello world"` | Notes containing "hello world" |
| `-"hello world"` | Notes not containing "hello world" |
| `foo "some text"` | Notes with tag `foo` AND containing "some text" |
| `foo -bar "text"` | Notes with `foo`, without `bar`, containing "text" |
| `"say \"hi\""` | Notes containing `say "hi"` |

## Edge Cases

- Empty query: valid, matches all notes (or no-op)
- Only whitespace: same as empty
- `"unclosed` : warning, term omitted, search does not execute
- `""`: warning, empty quoted string is invalid
- `-` or `+` alone: invalid/incomplete term