# PLAN.md — Tag Ontology / Implication Rules

This plan adapts the original “tag ontology + rule system” idea to MetaList’s current architecture.

## Current Reality (already in the codebase)

- Tags are stored as a single tag-bar string in `notes.tags`.
  - Tokenization: `app/services/content_formatting.py:_tokenize_tag_bar()`.
- The server already computes **hierarchical tag inheritance**:
  - Descendants inherit **ancestor non-meta tags**.
  - Implementation: `app/services/note_store.py`.
  - Coverage: `tests/unit/test_tag_inheritance.py`.
- Search uses an in-memory index built from:
  - plaintext note content
  - “effective tag terms” (explicit + inherited)
  - Implementation: `app/services/search_index.py`.

This feature adds **ontology rules** on top:

- A directed implication graph `A => B` over tags.
- Optional matcher rules (content/tag conjunction → tag).
- A UI that explores the implication graph around a focus tag and edits rules.

---

## Decisions (confirmed)

- **Tag tokens are primitive**: no `#tag` prefix anywhere.
- **Operators in v1**: `=>` and `=`.
  - `A = B` is syntactic sugar for `A => B` and `B => A`.
  - No association (`~`) in v1.
- **No negation** in rule LHS (avoids “matches almost everything” traps).
- **Matcher rules run on plaintext content** (derived from note HTML).
- Plaintext is defined as `strip_html(content_html)` (see `app/utils/text_utils.py`).
- **Tags are case-sensitive** (match current behavior).
- **Rule source in v1**: a single human-editable UTF-8 text file at repo root (server restart required after edits).

---

## Definitions (aligned with existing code)

- **Explicit tags**: authored in the tag bar (`notes.tags`).
- **Inherited tags**: non-meta tags inherited from ancestors (already implemented).
- **Base effective tags**: explicit ∪ inherited (what search currently indexes).
- **Inferred tags**: tags derived from ontology rules per note.
- **Effective tags w/ ontology**: base effective tags ∪ inferred tags.

---

## Phase 0 — Finalize DSL + Semantics (spec-first)

### Goals
- Make the rule language unambiguous and easy to edit.
- Keep server behavior fail-fast on invalid rules.
- Define exactly how inference composes with hierarchical inheritance.

### Proposed DSL (v1)

One rule per line:

    LHS => RHS
    LHS = RHS

Comments:
- Blank lines are ignored.
- Comment-only lines start with `#` or `//`.
- No inline comments in v1.

Where:
- `RHS` is a single tag token.
- `LHS` is either:
  - a single atom, or
  - an AND-group: `(atom atom atom)`.

Atoms:
- `TAG`: a tag token (same token rules as the tag bar/search).
- `TEXT`: a simple quoted phrase (`"..."` or `'...'`) meaning substring match on note plaintext.
- `REGEX`: `/.../` optionally with flags (start with only `i`).

Initial constraints:
- No OR operator.
- No negation.

### Semantics

Per note (independent evaluation):
1) Start with base effective tags for that note.
2) Repeat until no new tags are added:
   - If a rule’s LHS is satisfied by (plaintext_content, current_tags), add RHS.
3) Tags only accumulate (fixed-point termination).

Plaintext matching:
- `TEXT` atoms match as whole-word patterns (word boundaries), equivalent to `/\bTEXT\b/`.
  - If the quoted phrase is all lowercase, it is treated as case-insensitive (equivalent to `/\btext\b/i`).
  - Otherwise it is case-sensitive.
- `REGEX` atoms run against the same plaintext; `/.../i` enables case-insensitive matching.

Composition rule:
- Hierarchical inheritance happens “below” ontology: ontology sees inherited tags as inputs.
- Ontology inference does not itself propagate along the tree; it runs per note.

### Deliverables
- Update `docs/design/ontology.md` to remove `#tag` assumptions and to explicitly mark `~` and multi-hop association search as “future”.
- Add a dedicated DSL doc if `docs/design/ontology.md` becomes too long (optional).
- Define canonical tag token rules by referencing `docs/ui/tag-bar.md` + `docs/ui/search-syntax.md`.
- Define a parse error model (filename, line, column, message).

---

## Phase 1 — DSL + Parser + File Loader (scaffolding)

### Goals
- Load rules from a **human-editable text file**.
- Parse rule lines into a strict AST.
- Build compiled indices for fast inference + UI graph queries.
- Unit-test parsing and error reporting.

### Rule source (v1)

- File path: `ontology_rules.txt` (repo root).
- Edits require a server restart.
- This loader is **temporary scaffolding** and is expected to be removed later (DB-backed rules and/or UI editor).

Loader behavior:
- If `ontology_rules.txt` is missing: treat as “no rules” (empty rule set).
- If file exists but has parse errors: fail-fast on startup with a precise error.

### Proposed code
- `app/services/tag_ontology.py` (new): parser + compiler + core engine types.
- `app/services/ontology_rules_loader.py` (new): file reading + wiring into a singleton engine.

### Compilation outputs
- `implication_edges`: `TAG => TAG` rules where LHS is exactly one TAG atom.
- `out_edges[tag]`, `in_edges[tag]`.
- `matcher_rules`: everything else.
- Optional indices for speed:
  - `rules_by_required_tag[tag]`.

### Tests
- `tests/unit/test_tag_ontology_parser.py` (new).

---

## Phase 2 — Integrate Ontology Inference with Search (no UI)

### Goals
- Make ontology rules affect search results without changing the tag-bar UX.
- Keep behavior correct under tag edits, moves, and content edits.

### Integration points

**Full rebuild integration (startup/login)**

Current flow:
- `populate_cache_from_db()` → `note_store.load_from_db()` → `search_index.rebuild()`.

Add:
- load + compile ontology rules
- for each note, compute `effective_tags_with_ontology`
- feed those terms into `SearchRecord.tag_terms` in `NoteStore.load_from_db()`.

**Incremental update integration (NoteStore)**

Hook into existing centralized mutation paths:
- `NoteStore.update_note_from_db(...)`:
  - content changed: recompute inferred tags for that note.
  - tags changed: recompute inferred tags for that note + descendants (base tags change via inheritance).
- `NoteStore.update_metadata_from_db(...)`:
  - move/parent change: recompute inferred tags for moved subtree.

Use `search_index.bulk_update_tag_terms(...)` for subtree updates.

### Tests
- Extend `tests/unit/test_tag_inheritance.py` to assert ontology inference composes with inheritance.
- Add tests for “ancestor tag edit changes descendant inferred tags”.

---

## Phase 3 — Persistence (SQLite) (before any UI)

### Goals
- Store rules in SQLite.
- (If/when encryption is enabled) store rules encrypted at rest.

### Proposed schema

New table (name TBD, e.g. `ontology_rules`):
- `id INTEGER PRIMARY KEY`
- `rule_text TEXT NOT NULL`
- `rule_encryption_nonce BLOB`
- `rule_encryption_tag BLOB`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Storage pattern:
- Encryption enabled: `rule_text` stores base64 ciphertext + nonce/tag populated.
- Encryption disabled: `rule_text` stores plaintext + nonce/tag NULL.

### Important timing constraint

If encryption is enabled, rule text cannot be decrypted at process start (no DEK).
Rules must load after the auth login endpoint (i.e., after `set_session_dek(dek)` has run).

### Proposed code
- `app/db/schema.py`: create/ensure the new table.
- `app/db/ontology_sql.py` (new): CRUD helpers.
- `app/services/ontology_service.py` (new): encrypt/decrypt + parse + compile.
- Mirror the existing “cache is ready” pattern used by `auth_cache_state`.

### Migration path (scaffolding → DB)

- Add a one-shot importer that reads `ontology_rules.txt` and writes rows to SQLite.
- Once DB load is stable, remove (or disable) the file loader.

---

## Phase 4 — UI + API (single “real” UI, no intermediate explorer)

### Goals
- Provide a UI that both:
  - explores the implication graph around a focus tag, and
  - edits ontology rules (create/update/delete rule lines).
- No separate “read-only explorer” milestone.

### Graph view requirements

- The focus view shows:
  - left: all tags that (transitively) imply the focus (predecessors)
  - middle: focus SCC (equivalence class)
  - right: all tags implied by the focus (successors)
- SCC is computed over implication edges.

### API surface (under existing `API_PREFIX`, currently `/api2`)

- `GET /ontology/focus?tag=...` → `{left: [...], middle: [...], right: [...]}`
- `GET /ontology/rules` → `{rules: [{id, text}]}`
- `POST /ontology/rules` (create)
- `PUT /ontology/rules/{id}` (update)
- `DELETE /ontology/rules/{id}`

Server behavior:
- All writes validate by recompiling the full rule set; reject on any parse error.
- Recompile swaps in atomically.
- After successful recompile, recompute ontology-derived tags for search index and refresh views.

### Code
- `app/api/routes/ontology.py` (new router).
- `app/main.py`: include router under `API_PREFIX`.
- `app/static/js/modules/modals/ontology-modal.js` (new) or a dedicated panel.
- Wire into command palette / keybinding.
