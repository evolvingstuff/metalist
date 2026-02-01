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
- **Rule source (current)**: SQLite-backed rules table, cached in-memory.
  - Legacy `ontology_rules.txt` is treated as an importer seed (only if the DB table is empty).

## Read Guard Principle (critical)

MetaList’s core principle is: **DB reads happen only at startup (or explicit rare maintenance windows).**

- Normal runtime operation must not `SELECT` from SQLite.
  - Enforced by the post-startup read guard described in `docs/design/in_memory_store.md`.
- Writes (`INSERT`/`UPDATE`/`DELETE`) are allowed during runtime.
- For ontology rules specifically:
  - A single startup load hydrates an in-memory cache.
  - All API reads are served from the in-memory cache.
  - All API writes update SQLite + update the in-memory cache (no read-back).

---

## Definitions (aligned with existing code)

- **Explicit tags**: authored in the tag bar (`notes.tags`).
- **Inherited tags**: non-meta tags inherited from ancestors (already implemented).
- **Base effective tags**: explicit ∪ inherited (what search currently indexes).
- **Inferred tags**: tags derived from ontology rules per note.
- **Effective tags w/ ontology**: base effective tags ∪ inferred tags.

---

## Phase 0 — Finalize DSL + Semantics (spec-first)

Status: ✅ DONE (implemented in `app/services/tag_ontology.py` + docs in `docs/design/ontology-rules-v1.md`).

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

Status: ✅ DONE (parser/compiler complete; file-loader approach superseded by DB store).

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

Status: ✅ DONE (NoteStore computes ontology-inferred tag terms for search).
Notes:
- Test coverage exists for search + inference (`tests/unit/test_tag_ontology_search_integration.py`).
- Inheritance × ontology composition tests can be expanded later if needed.

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

Status: 🟡 IN PROGRESS (core implemented; see “Remaining Work”).

### Goals
- Store ontology rules in SQLite.
- Keep runtime reads at zero (cache at startup).
- If encryption is enabled: keep rules encrypted at rest.

### Schema (implemented)

Table: `ontology_rules`:
- `id INTEGER PRIMARY KEY`
- `rule_text TEXT NOT NULL`
- `rule_encryption_nonce BLOB`
- `rule_encryption_tag BLOB`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Implemented in:
- `app/db/schema.py`
- `app/db/ontology_rules_sql.py`

Storage pattern:
- Encryption enabled: `rule_text` stores base64 ciphertext + nonce/tag populated.
- Encryption disabled: `rule_text` stores plaintext + nonce/tag NULL.

### Important timing constraint (handled)

If encryption is enabled, rule text cannot be decrypted/compiled at process start (no DEK).

Implementation approach:
- Startup loads rule rows into memory, but if any are encrypted the ontology engine stays “not ready”.
- After login (`set_session_dek(dek)`), decrypt + compile once, then serve from memory.

### Code (implemented)
- DB schema + CRUD: `app/db/schema.py`, `app/db/ontology_rules_sql.py`
- In-memory cached store + compiler: `app/services/ontology_rules_store.py`
- Startup bootstrap: `app/main.py`
- Post-login decrypt/compile hook: `app/api/routes/auth.py`
- Password transitions encrypt/decrypt rules too: `app/services/auth_service.py`

### Migration path (scaffolding → DB)

Implemented:
- On startup, if `ontology_rules` table is empty, import non-comment lines from `ontology_rules.txt`.

Remaining:
- Decide whether to keep `ontology_rules.txt` around long-term (as a backup/export), or remove it.
- If removed, update any docs that still mention file-backed rules.

### Remaining Work (Phase 3)

- Enforce/verify “no runtime reads” for ontology rules:
  - Confirm ontology API never calls `connect_reader(...)`.
  - Optionally add a small regression test that read guard trips if a runtime SELECT is introduced.
- Decide final encryption behavior for rule writes:
  - Current behavior encrypts rules when a DEK is available (token/global DEK).
  - Confirm we want to *require* encryption when `encryption_enabled=1` (vs allowing plaintext rule rows).
- Add a minimal UI/UX affordance for “ontology not ready until login” (only relevant when encryption is enabled).

---

## Phase 4 — UI + API (single “real” UI, no intermediate explorer)

Status: ✅ DONE (API endpoints + UI modal are implemented).

Notes:
- Rule IDs are SQLite IDs (not contiguous line numbers). Frontend treats them as opaque integers.

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
- Backend routes: `app/api/routes/ontology.py`
- UI modal: `app/static/js/modules/modals/ontology-modal.js`
- Shortcut: `Cmd+;` (and `Ctrl+;`) in `app/static/js/modules/mode-manager/events/keyboard-events.js`

---

## Session Handoff Notes

### What’s Done (high level)

- Phase 0/1/2/4 implemented: DSL + parser/compiler + search integration + UI/API.
- Phase 3 mostly implemented: rules stored in SQLite and cached in memory (startup load, runtime write-only).

### New/Changed Core Files (Phase 3)

- `app/db/schema.py`
- `app/db/ontology_rules_sql.py`
- `app/services/ontology_rules_store.py`
- `app/main.py`
- `app/api/routes/auth.py`
- `app/api/routes/ontology.py`
- `app/services/auth_service.py`
- `app/usecases/rename_tag.py`

### Tests Added (Phase 3)

- `tests/unit/test_ontology_rules_store_sqlite.py`

## Known Local Tooling Notes

- `./sanitycheck/run` currently fails locally unless the repo’s sanitycheck deps are installed (it asks for `./sanitycheck/install.sh`).
- `pytest` currently has known failures unrelated to ontology work; don’t treat them as regressions from this feature.
  - `tests/unit/test_snapshot_search_negative_terms.py`
  - `tests/unit/test_undo_state_edit_mode_coalescing.py`
