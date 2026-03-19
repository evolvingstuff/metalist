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

In addition, notes implicitly inherit **non-meta** tag terms from their ancestors:
- A note’s effective tags are: its own tag terms **plus** all ancestor tag terms that do **not** start with `@`.
- Tags starting with `@` (meta tags like `@monospace`) are **not** inherited.
- Tag-bar `/* ... */` comments are **not** inherited (they only affect text search for the note that contains them).

Ontology rules also add **inferred tags** before search matching:
- Implication + matcher rules are applied per note, and inferred tags are added to the effective tag set.
- See `docs/design/ontology-rules-v1.md` for the rule language and semantics.

### Search Suggestions
- Search-bar tag suggestions are segment-aware for connector-separated tags.
- For a blank query only, the top 3 suggestion slots can be promoted from persisted interacted-search history for the active namespace.
- That history stores ordered positive tag-query sequences, credits only after a qualifying interaction against that active result set, and decays on each newly credited interaction rather than over wall-clock time.
- Qualifying interactions include server-backed note actions performed while the executed search is active, plus qualifying scroll persistence.
- A typed prefix can match either the start of the full tag or the start of any connector-separated segment.
  - Example: `wor` suggests `workspaces` and `databricks-workspaces`.
  - Example: `orksp` suggests neither.
- This affects suggestions only; actual tag search matching remains exact against effective tag terms.

### Text Terms (quoted)
- Required text: `"some text"` or `'some text'`
- Forbidden text: `-"some text"` or `-'some text'`

Text matching is:
- Case-insensitive (`casefold`).
- Against **visible text**, extracted by stripping HTML (scripts/styles ignored).
- Also against tag-bar `/* ... */` comment text (whitespace-normalized).

### UUID Terms
- UUIDs in positive terms are treated as direct note targets (including when pasted as `[[UUID]]`).
- This is additive with normal tag/text matching.

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
- All descendants of a matching note are included (so the full subtree under a match is visible).
- Within a visible root, excluded siblings/branches are rendered as redacted placeholders on the client (fixed-height grey lines) rather than disappearing.
- For UUID-direct targeting specifically:
  - The target note is included.
  - Its ancestors are included.
  - Its descendants are included and not redacted.
  - Non-matching sibling branches remain redacted according to normal search behavior.

## Windowing / Infinite Scroll

Results are still **windowed by root notes**:
- The server sends an initial window of matching roots.
- Scrolling near the end triggers additional root windows.

## Embedded References and Search

Embedded note references (`![[UUID]]`) are rendered in view mode only and do not alter search matching rules:
- Referenced note tags do not add required/forbidden tag hits for the host note.
- Referenced note text does not add required/forbidden text hits for the host note.
- Search matching remains based on the host note data + existing inheritance/ontology behavior.
