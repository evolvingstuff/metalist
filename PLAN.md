# PLAN.md — CLI-like Settings / Menu / Preferences Palette

Goal: Build a fast, keyboard-first, CLI-like palette for configuring preferences, view state, and simple actions in a PKMS.  
Design is consistent with the app’s existing **flat, AND-based search semantics**.

Target UX:
- Open with a single shortcut (e.g. Cmd+/)
- Reach any endpoint in ~3–4 keystrokes
- No hierarchy, no OR/NOT, no commands-as-language
- Same mental model as search elsewhere in the app

Non-goals:
- No command execution language
- No hierarchical settings pages
- No auto-generated tags
- No architecture- or framework-specific decisions

---

## 0) Core concepts & vocabulary

### Palette
An overlay UI containing:
- Query input
- Suggested tags (facets)
- Matching endpoints rendered as interactive rows

### Endpoint
A single configurable or executable unit. One of:
1. **Boolean** — persistent on/off
2. **Select** — choose exactly one option from a finite set
3. **Action** — one-step commit, no extra input
4. **Form action** — requires additional input and/or validation (opens a form/modal)

### Tag (facet)
A manually authored keyword. Query tokens are matched via boolean AND across tags.

### Query semantics
- Tokens are unordered
- All tokens must match
- No OR
- No negation
- Input is an unordered bag of words

---

## 1) Design principles (do not violate)

- Flat > hierarchical
- AND-only > expressive query language
- Discoverability via tags, not navigation
- Configuration is data-driven, not code-driven
- Preference space is **qualitative and discrete**, not scalar
- Same query semantics as content search in the app

---

## 2) Endpoint taxonomy (frozen for v1)

### Boolean
- Persistent toggle
- Executed inline
- Keyboard: Space / Enter toggles

Examples:
- show backlinks
- auto-collapse long notes

---

### Select (1-of-N)
- Discrete, named alternatives
- No freeform values
- No multi-select

Examples:
- sort order (newest / oldest)
- theme (light / dark / system)

---

### Action
- Fully specified by current context
- Single-step commit
- No additional input required

Examples:
- expand all collapsed notes in current view
- collapse all notes in current view
- reset current view filters

---

### Form action
- Requires additional user input and/or validation
- Cannot be executed in one step
- Opens a form/modal/wizard

Examples:
- change password
- add/remove password protection

Note: “Form action” is a semantic category, not a UI mandate. Modal presentation is expected in v1.

---

## 3) Tag-mapping configuration (critical)

All **tag mappings** are defined in config files.

Endpoint definitions (kind/select options/labels/behavior) remain in code; config exists only to tune discoverability.

### Goals
- Adding or tuning discoverability is a data-editing task
- Tag iteration is cheap and encouraged
- No code changes required to adjust tags

### What config defines
For each endpoint id:
- `id` (stable, unique)
- `tags` (manually curated)

### What config does NOT define
- Business logic
- Side effects
- UI behavior or endpoint taxonomy (`kind`, `options`, etc.)
- Labels/descriptions
- Scope rules (`global` / `view` / `contextual`)
- Persistence mechanisms

### Runtime responsibilities
- Load and validate config
- Fail loudly in dev if:
  - config references an unknown endpoint id
  - an endpoint id has no tags mapping

Optional dev tooling:
- Config linter (duplicate ids, empty tags, unused tags)
- Dev overlay showing matched tags per result
- Hot reload of config during development

---

## 4) Matching & filtering semantics

### Tokenization
- Lowercase
- Split on whitespace
- Trim punctuation
- Ignore empty tokens

### Matching rule
An endpoint matches if **all query tokens** are contained in its tag set.

Label-word matching:
- Optional
- If enabled, treat as secondary/fallback only
- Tags remain the primary matching surface

---

## 5) Suggested tags (faceted narrowing)

Purpose: help users narrow large result sets without hierarchy.

### Behavior
- Empty query → show top-level suggested tags
- Non-empty query → suggest tags that:
  - Are not already in the query
  - Exist on currently matching endpoints
  - Reduce the result set

### Ordering
Blend of:
- Narrowing power
- Usage frequency of endpoints associated with tag
- Recency
- Alphabetical tie-break

Suggested tags:
- Clickable
- Keyboard-navigable
- Append token to query input

---

## 6) Result rendering (rows)

Each result row shows:
- Label
- Current value or affordance
- Optional secondary hint (description, scope, status)

### Boolean
- Checkbox-like
- Toggle inline
- Palette remains open

### Select
Choose one interaction style for v1:
- Inline cycle (← / →)
- OR popup list (Enter opens, arrows select)

Be consistent across all selects.

### Action
- Enter executes immediately
- Optional non-blocking feedback (toast / status line)

### Form action
- Enter opens form/modal
- Visual indicator that extra steps are required

---

## 7) Keyboard model (strict)

Global:
- Cmd+/ opens palette
- Esc closes palette or unwinds one level

Inside palette:
- Typing edits query
- Tab / Shift+Tab moves focus between regions
- Up / Down navigates within focused list
- Enter activates focused item
- Space toggles boolean
- Left / Right adjusts select (if inline cycling)

Modal behavior:
- Opening a form records prior focus + scroll
- Esc cancels and restores exact prior state
- Completion restores focus to originating row

---

## 8) Persistence rules

Requirement: preferences and view state survive reload/reset.

Guidelines:
- Each persistent endpoint has a persistence key
- Defaults applied only if no stored value exists
- Writes happen on change
- Correctness > optimization

Provide action endpoints for:
- Reset all preferences
- Reset current view configuration
- (Optional) Reset by facet/tag

---

## 9) Usage tracking & ranking

Track locally:
- Endpoint id
- Timestamp
- Optional query tokens at activation

Ranking model (simple):
- Frequency (recent window)
- Recency decay

Use ranking for:
- Empty query result order
- Tie-breaking
- Suggested tag ordering

---

## 10) Zero-results UX (important)

When no endpoints match:
- Explicit “no matches” state
- Identify likely offending token:
  - Remove one token at a time; see which restores matches
- Suggest near-miss tags (prefix / small edit distance)
- Keep logic simple; no full fuzzy search required

---

## 11) Tag authoring guidelines

For each endpoint:
- 3–8 core domain tags
- 3–8 synonyms / alternative phrasings
- Include:
  - verbs (show, hide, expand, collapse, sort)
  - nouns (notes, view, sidebar, editor)
  - user phrasing (reverse, newest, protect)

Manual curation is intentional and limited in scope.

---

## 12) Seed endpoint set (for early testing)

Booleans:
- Show backlinks
- Show tags in list
- Auto-collapse long notes

Selects:
- Sort order (newest / oldest / updated)
- Theme (light / dark / system)

Actions:
- Expand all collapsed notes in current view
- Collapse all notes in current view
- Reset current view filters

Form actions:
- Change password
- Enable / disable password protection

Ensure queries like:
- `sort reverse`
- `expand collapsed`
- `password protect`

all converge correctly.

---

## 13) Implementation order

1. Palette open/close + Esc unwind stack
2. Query input + tokenization + filtering
3. Result list rendering (all endpoint kinds stubbed)
4. Suggested tags computation
5. Keyboard navigation + focus management
6. Persistence for booleans/selects
7. Wire real actions to current view context
8. Form modal shell + one real form action
9. Usage tracking + ranking
10. Zero-results UX
11. Tests + regressions

---

## 14) Done criteria (v1)

- Any endpoint reachable via ≤3 obvious tokens + Enter
- Fully keyboard-operable
- Persistent across reload
- AND-only semantics everywhere
- Tags are authored in config files
- No hierarchy leaks into UX
- Behavior matches search semantics elsewhere in the app
