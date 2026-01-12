# Search Semantics

This document describes **server-side search behavior** (what matches what).

For input grammar, normalization rules, and completeness gating, see:
- `docs/ui/search-syntax.md`

## Term Types

Search queries are a whitespace-separated list of terms.

### Tag Terms (unquoted)
- `foo` and `+foo` are equivalent (required tag).
- `-foo` excludes notes that have tag `foo`.

Tag matching uses the note’s tag-bar string (`notes.tags`) tokenized with the same
rules as the tag bar:
- Wrapper tokens (e.g. `{{foo bar}}`) contribute inner terms (`foo` and `bar`).
- `/* ... */` comment regions are ignored.

### Text Terms (quoted)
- Required text: `"some text"` or `'some text'`
- Forbidden text: `-"some text"` or `-'some text'`

Text matching is:
- Case-insensitive (`casefold`).
- Against **visible text**, extracted by stripping HTML (scripts/styles ignored).

## Matching Rules

All required terms are AND-ed:
- A note must contain **every required tag**.
- A note must contain **every required text term** as a substring.

Forbidden terms exclude matches:
- A note must contain **none** of the forbidden tags.
- A note must contain **none** of the forbidden text substrings.

## Tree Inclusion

The UI renders a tree, so search returns context:
- All matching notes are included.
- All ancestors of a matching note are included (so matches are reachable).
- Descendants are included only when they themselves match.

## Windowing / Infinite Scroll

Results are still **windowed by root notes**:
- The server sends an initial window of matching roots.
- Scrolling near the end triggers additional root windows.

