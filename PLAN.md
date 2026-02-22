# PLAN.md — MCP Client Rewrite (Regex/Phrase-First, Fully Transparent, List-Based)

## 0. Goal
Replace the current MCP client flow with a new architecture optimized for:
- content retrieval first (quoted phrases + regex), not tag-guessing first
- safe regex execution (RE2 option)
- complete operator visibility into every LLM prompt/query/tool call
- list-based note processing with preserved ordering (bulk operations), no N-per-note hydration loops

This is a rewrite, not an incremental patch to the existing planner/tag pipeline.

## 1. Hard Requirements (Non-Negotiable)
1. Full transparency in UI (with hide/show controls):
   - every model prompt message
   - every tool call argument payload
   - every tool response payload
   - every intermediate generated query/pattern
   - raw model output
2. No hidden defaults that change behavior silently:
   - all behavior-driving parameters must be explicitly surfaced in UI/config and echoed in run metadata
   - any omitted value must fail fast or use an explicitly named profile
3. List-based note operations with preserved ordering:
   - do not fetch note details one-by-one for large result sets
   - use bulk hydration APIs/tools for note content/context retrieval
   - preserve deterministic ranking/order through retrieval, merge, hydration, and synthesis
4. Regex-first retrieval must support a safe engine option:
   - RE2-backed execution path for user/model-proposed regex patterns
5. Deterministic retrieval before synthesis:
   - model summarizes evidence after retrieval, not before
6. Search-context universe boundary:
   - if user has an active search context, it is the strict universe for the entire run
   - all MCP retrieval/hydration must be constrained to that context
   - if no active search context exists, universe is all notes

## 2. Scope

### In scope
- New client pipeline and UI telemetry model.
- New MCP tool contracts for bulk retrieval and regex search.
- Query planner redesign around lexical evidence (phrases/regex) with optional explicit tag atoms.
- Prompt/trace instrumentation with zero truncation in stored run data.
- Performance-safe result set handling for hundreds/thousands of hits.
- Migration path from old client logic to new client logic.

### Out of scope
- Note mutation/write actions.
- Ontology/tag management redesign.
- Multi-user auth or cloud deployment concerns.

## 3. Current Pain Points to Eliminate
- Tag-first guessing causes irrelevant expansions and brittle matching.
- Hidden/truncated prompts and payloads reduce debuggability.
- Planner behavior includes implicit assumptions/defaults that are hard to audit.
- Per-note follow-up calls do not scale for large result sets.

## 4. Target Retrieval Architecture

### 4.1 Pipeline stages
Stage 0 — Config snapshot (deterministic)
- capture and display every active setting used for this run
- persist in run log and UI “Run Config” panel
- capture `active_search_context_query` and derived `universe_mode`:
  - `scoped` when query is non-empty
  - `global` when query is empty

Stage 0.5 — Universe resolution (deterministic)
- resolve the run universe from `active_search_context_query`
- materialize ordered `universe_note_ids`
- all later stages must execute within `universe_note_ids` only
- no stage may expand beyond universe

Stage 1 — Query decomposition (LLM optional but fully visible)
- convert user request into explicit retrieval atoms only:
  - `phrase` atoms (quoted text terms)
  - `regex` atoms (`/pattern/flags`)
  - optional `tag` atoms (`tag:<term>` form only; `<term>` must be tag-like)
- no generic keyword-term atom type is allowed in rewrite mode
- output must be structured JSON; raw output retained
- tag-like term policy:
  - allowed pattern: `^[a-z0-9]+([._-][a-z0-9]+)*$`
  - no implicit conversion of plain words into tag atoms

Stage 2 — Deterministic retrieval plan expansion
- generate executable search operations from Stage 1 output
- operations are explicit and bounded (limit, offset, max patterns)

Stage 3 — Retrieval execution (list-oriented)
- run bulk searches via MCP tools
- collect ordered note-id lists + match metadata
- merge/intersect/rank deterministically while preserving stable list order semantics (not per-note loops)
- enforce intersection with `universe_note_ids` on every retrieval pass

Stage 4 — Bulk hydration
- hydrate note payloads in batches from resolved ordered note-id lists
- include only requested fields (content/context/tags/ancestors)

Stage 5 — Evidence synthesis
- LLM synthesizes from hydrated evidence
- synthesis prompt and evidence IDs shown in UI

### 4.2 Search strategy order
1. phrase exact matches
2. regex matches (RE2 mode if enabled)
3. optional tag-atom filtering/narrowing only when tag atoms are explicitly present

## 5. MCP Tool Contract Changes

### 5.1 Add `search_notes_regex`
Purpose:
- execute regex against note plaintext/context at scale

Arguments:
- `pattern` (string)
- `flags` (string; allowed subset only)
- `limit` (int)
- `offset` (int)
- `target` (enum: `content_text`, `context_text`, `both`)

Returns:
- `total_matches`, `returned_count`
- `results`: `note_id`, match spans/snippets, matched field

Rules:
- validate pattern and flags strictly
- fail fast on invalid/unsupported pattern
- no silent fallback engine
- require explicit scope input:
  - either `scope_query` or `scope_note_ids` (preferred: `scope_note_ids` for deterministic bounded universe)
- results must never include notes outside the provided scope

### 5.2 Add `get_notes_batch`
Purpose:
- fetch note details for many IDs in one call

Arguments:
- `note_ids` (array, deduped)
- `include_content_text` (bool)
- `include_context_text` (bool)
- `include_tags` (bool)
- `include_ancestors` (bool)

Returns:
- `total_requested`, `returned_count`, `not_found_ids`
- `notes`: structured payload per note

Rules:
- hard cap per batch call (configurable and surfaced)
- deterministic ordering by input ID order
- if `scope_note_ids` is provided, reject/ignore IDs outside scope deterministically (must be surfaced in response)

### 5.3 Keep existing `search_notes`
- keep for backward compatibility and optional explicit tag-atom pass
- stop forcing tag-centric planning behavior in client
- when used in rewrite mode, it must be universe-scoped (never global unless user context is empty)

## 6. RE2 Feasibility + Safety Plan
- Add optional dependency: `google-re2` (or repo-approved equivalent).
- Startup capability check:
  - if regex mode selected and RE2 unavailable, fail run with explicit error.
- Supported regex features documented; unsupported constructs rejected upfront.
- Add guardrails:
  - max pattern length
  - max alternation count
  - max execution candidate list size per pass

## 7. UI/UX Plan (Transparency First)

### 7.1 Trace panels (collapsible)
For each stage card, always include:
- `Prompt Messages` (full, untruncated)
- `Tool Request` (full JSON)
- `Tool Response` (full JSON)
- `Derived Query Objects` (full JSON)

### 7.2 Visibility controls
- global toggles:
  - show/hide prompts
  - show/hide tool payloads
  - show/hide raw JSON
- export run trace as JSON file

### 7.3 No truncation policy
- UI may collapse sections visually
- underlying stored payload must remain complete
- do not mutate payload with `...[truncated]...`

## 8. Performance Plan (List-Based)
- Retrieval stages operate on ordered note-id lists and scored maps.
- Hydration is chunked batch calls (e.g. 200 IDs/batch) not per-note calls.
- Add per-stage metrics:
  - candidate list length
  - hydrated list length
  - stage latency
  - payload size

## 9. Detailed Implementation Steps

Step A — Freeze and isolate old path
- keep old client path behind `legacy` mode switch
- add `rewrite` mode scaffold and route all new work there

Step B — Data contracts
- define strict Pydantic models for:
  - stage outputs
  - trace events
  - retrieval requests/responses
- remove implicit defaults from run payload model
- include explicit universe fields in run payload:
  - `active_search_context_query`
  - `universe_mode`
  - `universe_note_count`

Step C — MCP tool additions
- implement `search_notes_regex`
- implement `get_notes_batch`
- add schema docs and validation tests

Step D — Rewrite core pipeline engine
- implement deterministic stage runner
- each stage outputs typed artifact + trace entry
- enforce max-depth/step bounds explicitly
- enforce universe boundary at a single shared gate used by every retrieval tool adapter

Step E — Rewrite web UI integration
- consume stage stream events
- render collapsible full-payload trace panels
- add run-config snapshot + export JSON

Step F — LLM prompt redesign
- prompt focuses only on retrieval intent extraction and synthesis
- no hidden seed heuristics
- all prompt messages surfaced in UI
- planner output schema in rewrite mode allows only `phrase`, `regex`, and optional explicit `tag:<term>` atoms

Step G — Ranking and synthesis
- rank hydrated notes by lexical evidence
- feed bounded top-K evidence into synthesis prompt
- preserve provenance IDs in final answer metadata

Step H — Regression cleanup
- remove old tag-planner-specific code path after parity checks
- keep compatibility flag for one transition cycle

## 10. Testing Plan

### Unit tests
- regex validation, engine availability errors, invalid flag handling
- batch hydration behavior (stable ordering, deterministic dedupe, not-found handling)
- no-truncation trace persistence
- deterministic stage outputs

### Integration tests
- end-to-end query:
  - “what is my dad’s birthday?”
  - verify phrase/regex passes produce expected candidates
  - verify bulk hydration call count stays bounded (not N-per-note)
- large result set test (>=300 notes)
  - confirm no per-note hydration loop
- scoped-universe test:
  - set active search context (example: `work-journal -private -@password`)
  - verify every returned note ID is within scoped universe
  - verify out-of-scope matches are excluded even if phrase/regex would match globally

### UI tests
- trace panel show/hide toggles
- prompt/tool payload visibility
- exported JSON contains full payloads

## 11. Acceptance Criteria
1. A full run can be audited end-to-end from UI without hidden prompt/query behavior.
2. No payload truncation markers are introduced in stored trace artifacts.
3. For large result sets, hydration uses ordered batched MCP calls, not one call per note.
4. Regex retrieval supports RE2 mode with explicit fail-fast errors when unavailable.
5. Final answers include evidence provenance (note IDs and stage source).
6. Existing basic non-regex use still works in rewrite mode.
   - non-regex mode uses phrase atoms (and optional explicit tag atoms), not free keyword atoms.
7. When active search context is non-empty, all retrieval and hydration are strictly limited to that universe.

## 12. Risks and Mitigations
- Risk: RE2 packaging issues on some environments.
  - Mitigation: capability gate + clear startup diagnostics + phrase-only mode when regex mode is off.
- Risk: full payload visibility increases memory usage.
  - Mitigation: in-memory cap + optional persisted run logs + explicit payload size telemetry.
- Risk: rewrite destabilizes existing flow.
  - Mitigation: keep legacy mode switch until rewrite parity is validated.

## 13. Open Decisions Needed Before Implementation
1. Default rewrite mode toggle name (`rewrite`, `regex-first`, etc.).
2. Maximum batch size for `get_notes_batch`.
3. Whether regex pass should run before phrase pass or after phrase pass by default.
4. Whether context target for regex defaults to `content_text` or `both`.
5. Canonical source for active search context in client run payload (UI field vs fetched from server tab state).

## 14. Definition of Done
- All acceptance criteria met.
- New tests merged and passing.
- Legacy mode retained behind explicit switch for one transition cycle.
- Documentation updated for new tools, pipeline stages, and transparency controls.
