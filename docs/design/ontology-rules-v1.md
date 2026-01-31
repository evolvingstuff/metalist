# Ontology Rules (v1)

Status: implemented as Phase-1 scaffolding (file-backed + restart required).

## Scope

This document describes the ontology rule language currently implemented in:
- `app/services/tag_ontology.py`

Rules are loaded from:
- `ontology_rules.txt` (repo root)

Helpers:
- Parse/compile check: `parse_ontology_rules.py`
- Interactive query tool: `ontology_query.py`

## Syntax

One rule per non-empty, non-comment line.

Operators:
- Implication: `LHS => RHS`
- Equality: `LHS = RHS` (syntactic sugar for `LHS => RHS` and `RHS => LHS`)

Comments:
- Blank lines are ignored
- Comment-only lines may start with `#` or `//`
- Inline comments are not supported

### Tags

- Tags are plain tokens (no `#tag` prefix).
- Tags must be a single token with no spaces.

### LHS forms

LHS can be either:
- A single atom: `foo => bar`
- A conjunction group: `(atom atom atom) => bar`
  - Nested parentheses are not allowed in v1.

### Atoms

Allowed atoms on the LHS:

1) Tag atom

```
foo
```

2) Text atom (quoted)

```
"some phrase"
'some phrase'
```

3) Regex atom

```
/.../
/.../i
```

Regex notes:
- `/.../i` is case-insensitive.
- Escaping a literal slash inside the pattern uses `\/`.

## Semantics

Rules are applied per note as a monotone fixed point:
- Start with a set of tags.
- Repeatedly apply rules, only adding tags.
- Stop when no new tags are produced.

### Text atom semantics (word-boundary sugar)

Quoted text atoms are compiled as whole-word matches using `\b` boundaries.

- If the phrase is all-lowercase, it is treated as case-insensitive:
  - `"todo"` behaves like `/\btodo\b/i`
- Otherwise it is treated as case-sensitive:
  - `"TODO"` behaves like `/\bTODO\b/`
  - `"Todo"` behaves like `/\bTodo\b/`

This prevents accidental substring matches (e.g. `"TODO"` does not match `TODORS`).

## Testing

### Parse/compile check

```bash
.venv/bin/python parse_ontology_rules.py
```

### Interactive query tool

```bash
.venv/bin/python ontology_query.py
```

Behavior:
- If input is a single unquoted tag token: shows left/equal/right graph view.
- Otherwise: treats unquoted tokens as tags, and quoted strings as plaintext, then shows inferred tags.

