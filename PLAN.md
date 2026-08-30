# PLAN — User-Assisted Scoped Search

## Status

Implemented; automated regression checks pass and the feature is awaiting human
UI/Ollama validation. This plan replaced the production agent-wide MetaList search
loop with the user-bounded, iterative investigation loop described below.

## Outcome

When the user asks a question, MetaList can investigate only the note-result scope
the user is actively viewing. The server freezes that scope at Send time, pages
through it in the same deterministic order as the UI, and lets the agent narrow or
backtrack within that boundary. The model carries a bounded, structured working
summary rather than accumulating every page it has read. Before answering, MetaList
rehydrates the important original sources so final prose is based on authoritative
note content rather than lossy working memory.

The target loop is:

```text
question + frozen user scope descriptor
        ↓
high-level route: respond directly or investigate current scope
        ↓
first bounded page + whole-scope ranked tag facets
        ↓
one structured Instructor step:
  update working summary
  assess evidence sufficiency
  choose next investigation action
        ↓
execute action inside the frozen boundary
        ↓
replace old page with current page/state/summary
        ↓
repeat until sufficient
        ↓
rehydrate selected authoritative sources
        ↓
stream final answer with allowlisted references
```

## Accepted Product Decisions

1. The active result scope is frozen when the user sends the message. Later UI
   searches, tab changes, or navigation do not alter the running investigation.
2. Gray-bar/search-redacted nodes are outside the evidence set and can never be
   discovered by a later agent refinement. Contentless ancestor objects may be
   retained solely to preserve the nested path to matching evidence.
3. Direct note reopening is allowed only for sources already shown to the agent in
   the current investigation.
4. Tag facets report both matching-note and matching-result-tree counts so their
   effect is not ambiguous in a hierarchical result set.
5. Facets are bounded and ranked by frequency across the entire current result
   state. Each evidence note on the current page exposes both its exact
   user-assigned tags and its locally assigned/inferred search tags, including
   tags that do not appear in the bounded overall facet summary. Parent and
   ancestor tags apply to descendants by hierarchy and are not repeated on each
   child payload.
6. Regex is not an initial action. The architecture leaves a safe extension seam,
   but phase one supports tag and exact-text refinements only.
7. Final synthesis rehydrates the original sources selected to support the answer.
8. Existing redaction remains absolute. Search-redacted notes and protected note
   values do not enter pages, facets, working summaries, final evidence, or traces.
9. Prompt examples and UI labels use MetaList's real tag grammar. Typical tags are
   unquoted, often hyphenated tokens such as `this-is-typical-tag`,
   `project-foo`, or `system-performance`; the plan does not teach hash prefixes or
   slash-delimited forms as conventional merely because the parser permits them.
   All validation and normalization defer to MetaList's existing tag parser and
   search semantics.

## One Approval Assumption

An empty normal search is treated as a valid user scope containing every
agent-visible, non-redacted note in the current namespace. The chat UI must label
this explicitly as `All notes`; it must never be represented as an absent or
unbounded scope. Approval of this plan includes approval of that behavior.

## Non-Goals

- No embeddings, vector database, conventional top-k RAG, or corpus-wide semantic
  retrieval.
- No escape from the user-created scope to the rest of the PKMS.
- No regex action in the initial release.
- No note creation, editing, movement, deletion, tagging, or other mutation.
- No durable investigation summaries, traces, or source caches.
- No LiteLLM, automatic provider routing, fallback, or cost-accounting layer.
- No silent reuse of the existing global-search action under a new UI label.

## Architectural Invariants

### Scope enforcement

- `S0` is an immutable, server-owned snapshot of the eligible matching note nodes
  and their ordered result trees at Send time.
- Every agent-generated state `St` must satisfy `St ⊆ S0`.
- Scope membership is enforced by the search service/tool layer, not by prompting.
- The client supplies a view descriptor, never a trusted list of eligible UUIDs.
  The server resolves membership using the same in-memory search, date-filter,
  temporary-view, hierarchy, and root-ordering semantics used by `/notes/view`.
- Normal search, empty/all-notes view, Untagged notes, and temporary Reference
  source contexts must each resolve to an explicit scope kind.
- Sort mode controls the frozen root order but never changes membership by itself.
- Only explicit search matches are eligible. Ancestors rendered for reachability
  and gray/redacted sibling or descendant placeholders are not silently promoted
  into the agent scope.
- The frozen snapshot retains immutable references to the searchable text, exact
  tags, locally inferred searchable tags, hierarchy IDs, timestamps, and ordering needed
  for deterministic run-local refinement. A later note edit cannot silently change
  what this in-flight investigation searches.
- Every evidence page is serialized as root note JSON objects with recursively
  nested `children`; it is never flattened into an unrelated note array.

### Redaction and privacy

- Search-redacted nodes are excluded before tag aggregation or page construction.
- Protected values retain the existing replacement/exclusion behavior before the
  snapshot is made available to any agent component.
- Facet counts cannot disclose tags belonging only to excluded/redacted notes.
- Agent Debug remains session-only. Exact detail may show only content that was
  legitimately inside the current investigation boundary.

### Context growth

- Previous page payloads are replaced, not appended, after their relevant evidence
  has been incorporated into the working summary.
- Each decision call receives only canonical conversation, the current question,
  fixed scope metadata, current refinement state, current ranked facet page,
  bounded working summary, and current note page.
- The runtime validates the working-summary size and field/count bounds before it
  accepts the next action.
- Working summaries and scope state are transient and never enter later canonical
  conversation history.

### Evidence and references

- Every retained fact, tentative conclusion, and contradiction carries one or more
  observed source IDs where evidence exists.
- Source IDs in working memory must be a subset of IDs actually shown during the
  run. Invented or merely guessed UUIDs fail validation.
- `reopen_sources` can access only observed IDs.
- `answer` supplies a bounded set of observed source IDs that MetaList rehydrates
  automatically for final synthesis.
- Final response citations remain restricted to exact rehydrated, non-redacted
  source notes. The visible References UI remains root-deduplicated, while its
  navigation query retains cited child UUIDs so unrelated siblings stay redacted.

## Proposed Run-Local Models

All request/response fields remain required. Pydantic models should reject missing
fields and invalid cross-field combinations at the boundary.

### `AgentScopeDescriptor`

Client-visible description of the active UI state submitted with the chat turn:

- scope kind: normal search, all notes, or untagged;
- visible active tab ID and originating scope tab ID;
- displayed search text or required empty placeholder;
- date-filter signature/state;
- sort mode;
- empty compatibility reference-ID list for current clients;
- client-visible label used by the chat scope indicator.

The server validates this descriptor against authenticated namespace/tab state and
resolves the real member set itself.

### `ScopedSearchSnapshot`

Immutable server-only run state:

- scope ID/run ID;
- normalized descriptor;
- ordered eligible root IDs;
- ordered eligible note IDs within each root;
- frozen parent/child paths used to serialize recursive result-tree objects;
- frozen searchable note records;
- whole-scope note and result-tree counts;
- complete normalized tag-frequency index;
- creation timestamp and namespace/session ownership.

The snapshot is in memory only and is cleared when the run completes, fails, is
cancelled, or the session/runtime is purged.

### `InvestigationState`

Mutable run-local navigation state:

- immutable `S0` reference;
- current subset/state ID;
- refinement stack with disclosed state IDs for backtracking;
- current one-based note-result page;
- current tag-facet page;
- observed source-ID set;
- current structured working summary;
- step count and context-budget accounting.

Each refinement creates a new subset state and resets the note page to one.
Backtracking restores a disclosed prior state, never a state outside `S0`.

### `WorkingSummary`

A bounded ranked source set rather than a prose summary. Each entry has only an
exact current-page `note_id` and a 1–100 `importance` score for the user's request.
Each page is rated without exposure to earlier page scores. MetaList validates
current-page provenance, merges and deduplicates ratings programmatically, keeps
the highest score for repeated IDs, sorts descending, and retains the best 64.
On `answer`, the top 32 are expanded as candidate evidence; the final writer may
use and cite any supporting subset and must not cite unused candidates.

### `InvestigationStep`

One Instructor-validated model response updates working memory and chooses exactly
one next action:

- current-page `working_summary` ratings;
- `action_kind`;
- required flat action-argument placeholders compatible with Ollama JSON Schema;
- compact reason;
- explicit evidence-sufficiency assessment;
- no separate answer-source list; `answer` uses the accumulated top 32.

Summary update and action choice happen in one structured call. Do not add a
separate summarization inference call per page.

## Initial Action Set

### `page_next`

- Advances one page in the current subset.
- Fails validation when no next page exists.
- Carries only the updated summary into the next call; the old page is removed.

### `refine_tags`

- Applies a validated tag-only expression to the current subset.
- Supports required tags, AND/OR combinations, and exclusions using existing
  normalized MetaList tag semantics.
- Uses ordinary unquoted MetaList tag tokens such as `project-foo`; examples must not
  present hash prefixes or slash-delimited notation as the conventional form and
  must match `docs/ui/search-syntax.md`.
- Every referenced positive/excluded tag must exist in the frozen scope catalog
  and must have been disclosed through a facet page or exact per-note tags.
- Returns the new note/tree counts, first note page, and first ranked facet page.

### `refine_exact_text`

- Applies a bounded, non-empty, case-insensitive exact substring refinement to the
  current subset using the frozen visible/searchable text representation.
- Returns the new counts and resets paging.
- Does not accept regex syntax or silently interpret it as regex.

### `inspect_tag_facets`

- Pages through the frequency-ranked tag catalog for the current subset without
  changing note membership.
- Facet pages are deterministic and bounded.
- Allows the agent to discover less-common tags without injecting the entire tag
  vocabulary into every prompt.

### `backtrack`

- Returns to a disclosed prior refinement state, including the original `S0`.
- Restores that state's counts, page position policy, and tag facets.
- Preserves already merged note ratings; subsequent pages are still scored without
  seeing those prior ratings.

### `reopen_sources`

- Rehydrates a bounded list of previously observed note IDs for exact verification.
- Uses the frozen source records, not current mutable note state.
- Intended for exact wording, identifiers, dates, code, quotations, and resolving
  contradictions; it is not a general UUID lookup or scope bypass.

### `answer`

- Requires an explicit sufficiency reason.
- Automatically rehydrates the 32 highest-rated accumulated note IDs as candidate
  sources in the final synthesis context.
- Does not require the final writer to use or cite all 32; only notes actually
  supporting emitted claims become citations and References entries.
- May answer with explicit uncertainty; unresolved questions do not mechanically
  prohibit answering when the requested evidence burden is otherwise met.

### Deferred `refine_regex`

- Reserve an extension point but expose no schema enum value or UI/prompt action in
  phase one.
- A later design must select a timeout-capable/safe regex engine and add expression,
  runtime, result, and context bounds before enabling it.

## Tag Facet Semantics

- Facets are computed across the entire current subset `St`, never only the visible
  note page.
- Counts include:
  - unique eligible matching notes carrying the effective searchable tag;
  - unique eligible result trees containing at least one such note.
- Case-equivalent tags collapse to one facet using deterministic display spelling.
- Default ordering is descending matching-note count, then descending matching-tree
  count, then case-insensitive tag text for stability.
- Exact per-note payloads retain the note's user-assigned tags in their original
  order/spelling, independently of facet truncation and ranking.
- Agent tag behavior is deliberately literal: facets, per-note payloads, and later
  refinements use only directly assigned raw tags. Untagged notes omit `tags`;
  inherited, implied, and ontology-expanded tags are neither sent nor matched.
- Add a namespace-scoped `maximum ranked tags per facet page` control to AI Agent
  Settings. Use a bounded default and range justified by context-budget fixtures;
  do not serialize every namespace tag by default.

## Routing and Prompt Changes

- Keep the small high-level route call so ordinary questions, greetings, and
  general-knowledge requests can choose `respond` without loading note pages.
- Give that route a content-free snapshot of the exact active user search query,
  scope metadata, and result counts. Explicit requests to use the user's saved
  notes must be constrained by Instructor to `investigate_current_scope`.
- Replace high-level `search_notes` with `investigate_current_scope`.
- The base system prompt describes only when to respond directly versus investigate
  the user's frozen scope. It contains no detailed search grammar.
- Replace the current Search skill with a scoped-investigation skill containing:
  - hard-boundary semantics;
  - answer-sufficiency guidance for exact, existential, narrow factual, synthesis,
    and exhaustive questions;
  - working-summary mutation rules;
  - provenance requirements;
  - tag/exact-text/backtracking/paging examples using abstract `foo`/`bar`/`baz`
    and `"lorem ipsum"` data;
  - an explicit statement that page notes contain answerable content, not previews;
  - an explicit statement that each note's exact tags may contain useful tags absent
    from the ranked facet page.
- Instructor continues to own every structured route/investigation call. Direct
  Ollama streaming remains limited to final prose.
- Bound every generation over the wire (512 route; 2,048 investigation; 1,024
  query; provider-specific final prose at 1,024 for Ollama and 8,192 for OpenAI)
  and show a live approximate output-token count in eye mode. Treat provider
  truncation as an explicit failure.
- Use a flat required wire schema rather than a root union/reference layout, while
  preserving strong internal action models and semantic validators.
- Version the prompt/skill override contract. Existing saved overrides targeting
  the old action vocabulary must produce an explicit compatibility state in the
  prompt editor; they must not be silently applied, silently deleted, or rewritten.

## Context Assembly

Refactor `AgentContextBuilder` from an append-only tool-result transcript into an
explicit per-step context builder:

```text
base system prompt
canonical conversation
active scoped-investigation skill
current question
frozen scope descriptor/counts
current refinement history/state
current bounded ranked tag facets
current working summary
current page or reopened source payload
structured step instruction
```

The next call rebuilds this context with the replacement summary and new page. It
must not contain prior raw pages, prior summary versions, or discarded refinement
payloads. Agent Debug still records every exact outbound request at the moment it
was made.

Final synthesis receives:

```text
base system prompt
canonical conversation
current question
final working summary
verified authoritative source payloads
scope/coverage statement
final response instruction
```

## Search and State Services

Introduce focused services rather than putting scope logic in the FastAPI route:

- `app/services/agent/scope.py`
  - validate/resolve UI scope descriptors;
  - freeze ordered eligible records;
  - enforce session/run ownership and redaction boundaries.
- `app/services/agent/investigation.py`
  - hold `InvestigationState`;
  - calculate pages and counts;
  - execute refinements/backtracking/facet paging;
  - validate observed-source access;
  - replace and bound working summaries.
- Refactor `app/services/agent/tools.py` into thin read-only adapters over those
  services; do not query SQLite.
- Reuse `SearchIndex`, `NoteStore`, `resolve_search_scope`, root ordering, date
  filtering, tag parsing, ontology/inheritance, and existing note serialization
  helpers rather than cloning their semantics.
- Keep all investigation state in memory and clear it on completion, failure,
  cancellation, Clear Chat, logout, runtime lock, and server restart.

## API and Frontend Scope Capture

- Extend the required AI chat request with a validated active-scope descriptor.
- At Send time, the chat controller reads the current ModeManager/tab state,
  search text, date filter, and sort mode. A temporary Reference source supplies
  its retained originating scope instead of replacing that scope with the UUID
  navigation query.
- The server cross-checks client claims against authenticated tab/temporary-view
  state and resolves the authoritative membership set.
- Do not send thousands of note IDs from the browser.
- Render a persistent scope header/chip on the user turn or assistant run:

  ```text
  Scope · project-foo · 834 notes in 217 result trees
  ```

  Empty search renders `Scope · All notes`; untagged scope uses its established
  label. The displayed scope remains the captured scope even if the user navigates
  elsewhere while the run continues.
- Scope metadata is session-only transcript/debug state and is excluded from later
  canonical model history.

## Diagnostic and Debug UX

- Preserve the default-hidden eye-mode contract and compact hidden-mode progress.
- Add distinct lifecycle panels that update in place for:
  - freezing/readying the active scope;
  - inspecting a note page;
  - updating the working summary and selecting the next step;
  - applying a tag or exact-text refinement;
  - paging tag facets;
  - backtracking;
  - reopening sources;
  - verifying evidence and writing the answer.
- Completed panels should report useful concrete state, such as current/total result
  trees, matching-note counts, page position, refinement syntax, retained summary
  size, and selected action reason.
- Every panel retains the separate approximate input-token count already carried by
  `action_status` events.
- Agent Debug records:
  - the resolved immutable scope descriptor and counts;
  - every state transition and subset count;
  - every working-summary replacement;
  - every action reason and argument;
  - exact request/response payloads for every structured step and final synthesis;
  - bounded page/tool payloads, source reopens, retry information, and timing.
- Debug data remains session-only and never becomes canonical conversation history.

## Configuration

Retain namespace-scoped controls separately for Ollama and OpenAI:

- maximum characters per note;
- approximate serialized-input tokens per evidence page (Ollama default 5,000;
  OpenAI default 24,000), with greedy root-atomic packing and variable root
  counts;

Add:

- maximum ranked tags per facet page;
- bounded working-summary character budget.

Choose and document conservative defaults/ranges using representative large-scope
fixtures before implementation is considered complete. Final-source rehydration
uses the existing per-note/page character limits and an explicit source-count bound
validated by the investigation schema.

## Implementation Phases

### Phase 1 — Contract tests and frozen-scope service

1. Add failing tests for required scope request fields and server-side resolution.
2. Extract/reuse canonical search-scope resolution so `/notes/view` and the agent
   agree on membership and ordering.
3. Implement immutable `ScopedSearchSnapshot` creation for normal, all-notes, and
   untagged contexts; Reference source navigation retains its originating context.
4. Prove gray-bar nodes, protected content, unrelated roots, and post-Send UI changes
   cannot enter the scope.
5. Add whole-scope counts and deterministic root/note ordering tests.

Success: a run receives a frozen, ordered, redaction-safe `S0` resolved entirely on
the server from the active user context.

### Phase 2 — Facets, pages, and refinement state

1. Add effective-tag frequency indexes with note/tree counts and deterministic
   ranking.
2. Preserve exact user-assigned tags in every serialized page note.
3. Implement token-budgeted, root-atomic note pages and bounded facet pages.
4. Implement tag refinement, exact-text refinement, next-page, and state-stack
   backtracking with `St ⊆ S0` assertions.
5. Add observed-source tracking and restricted source reopening.
6. Add retrieval settings and the AI Agent Settings control for facet-page size.

Success: all navigation/refinement operations are deterministic, bounded, and
provably unable to escape the original scope.

### Phase 3 — Working memory and structured investigation step

1. Add required Pydantic working-summary/evidence models and size/provenance
   validators.
2. Add the flat `InvestigationStep` wire envelope and Instructor integration.
3. Build replacement step contexts; assert previous raw pages and old summary
   versions are absent from later outbound bodies.
4. Add the configurable working-summary budget.
5. Add retry/status/debug events for invalid summaries, invalid source IDs, and
   invalid actions.

Success: one structured call can revise working memory and choose the next action
without causing context to grow with total pages read.

### Phase 4 — Runtime loop and verified final synthesis

1. Replace `search_notes` route handling with `investigate_current_scope`.
2. Activate the scoped-investigation skill only after that route is selected.
3. Execute the bounded step loop with cancellation and maximum-step protection.
4. Enforce action-specific preconditions and backtracking/source rules in code.
5. On `answer`, rehydrate the declared observed sources and build final context from
   verified content plus the final summary.
6. Preserve citation allowlisting and child-preview replacement. Put exact
   `[[UUID]]` tokens beside evidence for the model to copy, programmatically number
   validated cited notes, then group the visible References UI by root without
   discarding the exact child UUIDs used for redacted reference navigation.
7. Remove the obsolete query-parameterization call, accumulated raw tool-result
   transcript, global duplicate-query guards, and dead action/schema code after
   parity tests pass.

Success: note-backed answers use only the frozen active scope, bounded rolling
memory, and reverified original sources.

### Phase 5 — Scope and investigation UI

1. Capture required scope state in the chat request.
2. Render the frozen scope label/counts with each run.
3. Add/update eye-mode activity panels for scope, page, summary, refinement,
   backtrack, reopen, sufficiency, and final response lifecycles.
4. Keep hidden-eye progress useful without exposing diagnostic query details.
5. Extend Agent Debug to show the exact frozen scope and chronological state changes
   after completion/failure.
6. Preserve Stop/Clear behavior and ensure both terminate the investigation and
   release run-local scope/summary state.

Success: the user can always see which scope was used, what the agent is doing, why
it chose an action, and how much context each diagnostic stage used.

### Phase 6 — Prompt editor compatibility, cleanup, and documentation

1. Replace the packaged Search skill with the scoped-investigation skill and update
   the high-level system/final prompts.
2. Add explicit compatibility handling for saved prompt/skill overrides built for
   the old action contract.
3. Ensure the prompt editor exposes the new skill with existing expand/collapse and
   Restore behavior.
4. Remove dead global-agent-search resources only after tests demonstrate no runtime
   references remain.
5. Update `docs/AI-SUMMARY.md`, `docs/design/agent-harness.md`,
   `docs/ui/ai-chat.md`, search semantics documentation, and testing documentation.

Success: code, editable prompts, settings, and documentation describe one coherent
scoped-investigation architecture with no hidden fallback to global search.

## Test Plan

### Unit and contract tests

- Chat requests fail when the scope descriptor is missing or malformed.
- Server resolution, not client UUID input, determines scope membership.
- Empty search resolves explicitly to all eligible non-redacted notes.
- Normal search/date/untagged scopes match the main view's membership and root
  order, including while a temporary Reference source is visible.
- Ancestors used only for UI reachability and gray-bar descendants are excluded.
- Protected values and their exclusive tags do not leak through facets or pages.
- Tag facets are computed over the full current subset, not the current page.
- Facets report correct unique note/tree counts and deterministic frequency order.
- Every page note exposes exact user-assigned tags even when absent from top facets.
- Tag/exact-text refinements remain subsets of `S0` and reset paging.
- Facet pagination does not change note membership.
- Backtracking restores a prior disclosed state and cannot escape `S0`.
- Reopening rejects unseen, outside-scope, duplicate, or malformed source IDs.
- Working-summary replacement rejects oversized fields, duplicate/unseen provenance,
  and invalid cross-field action data.
- Later wire requests omit prior raw pages and old summary versions.
- `answer` automatically rehydrates its declared source IDs.
- Final citations outside verified current-run evidence are stripped.
- Activity events always include approximate input-token metadata and merge lifecycle
  phases as intended.
- Session clearing/cancellation purges scope and investigation state.

### Behavior regressions

- `Are you there?` and general-knowledge questions choose `respond` without loading
  note pages or inheriting prior references.
- A note-dependent question cannot retrieve a highly relevant note outside the
  user's active scope.
- An exact lookup can answer after one authoritative hit and source verification.
- An existential question can stop after one convincing positive source.
- A narrow factual question can refine, backtrack, and answer from a few sources.
- A synthesis question can traverse several pages while keeping the effective
  context bounded.
- An exhaustive question continues until its stronger coverage requirement is met
  and accurately reports any remaining scope limitation.
- A rare tag visible on a current page can drive a later refinement even when it was
  absent from the ranked facet summary.

### Performance and budget tests

- Large synthetic scopes (including tens of thousands of notes and thousands of
  distinct tags) remain bounded in outbound prompt size.
- Facet aggregation and refinement operate on in-memory indexes without SQLite.
- Step `N` request size depends on current page plus bounded summary/facets, not the
  total content read in steps `1..N-1`.
- Defaults for facet-page and summary sizes fit comfortably inside the managed
  Ollama context alongside schema and final-source verification overhead.

### Required verification before each checkpoint

- Relevant focused Python tests.
- Relevant focused JavaScript tests.
- Full Python suite with the established intentional deselection.
- Full JavaScript unit suite.
- Python and JavaScript startup sanity gates.
- `git diff --check`.
- Human verification of the affected UI before any code checkpoint.

## Manual Acceptance Scenarios

1. Search `project-foo`, ask about a note that exists only outside that result set,
   and verify the agent reports insufficient scoped evidence rather than escaping.
2. Start an investigation, change tabs/searches while it runs, and verify its scope
   label, membership, and trace remain frozen.
3. Confirm a gray-bar descendant and its exclusive tags never appear in page data,
   facet counts, exact debug payloads, or the answer.
4. Use a scope with more tags than one facet page; verify common tags lead, a later
   facet page exposes rarer tags, and each note still shows all its exact tags.
5. Let the agent choose an unhelpful refinement, backtrack, and find the answer by a
   different tag or exact phrase.
6. Traverse several note pages and inspect Agent Debug to verify old raw pages leave
   subsequent wire requests while the structured summary remains.
7. Ask for an exact date/value/quotation and verify the selected source is reopened
   before the final response.
8. Open individual and combined AI References and verify a later AI reference
   replaces the active temporary query, follow-up chat retains the originating
   search scope, dismissible return behavior still works, and ordinary references
   followed inside notes still stack.
9. Cancel during a long structured step and verify Ollama work stops, the run records
   cancellation, and scope/summary state is released.

## Completion Criteria

- The user's active view is a hard, server-enforced retrieval boundary.
- Search pages and facets use the frozen current-view result membership/order.
- The agent can page, refine by tags/exact text, inspect more tags, backtrack, reopen
  observed sources, and answer; no regex action is exposed.
- Context remains bounded by current page, current facets, and one replacement
  working summary.
- Final answers are synthesized from rehydrated authoritative sources and retain
  trustworthy current-run References.
- Redacted/protected content cannot leak through content, metadata, counts, prompts,
  traces, or citations.
- UI and debug surfaces explain the frozen scope, every action/retry, evolving
  summary size, evidence sufficiency, and approximate input-token counts.
- Existing read-only, cancellation, non-persistence, prompt-editing, and managed
  Ollama guarantees remain intact.
- The provider-neutral inference seam additionally supports direct OpenAI API calls.
  API keys are write-only to the browser, encrypted at rest only when the namespace
  itself is encrypted, and otherwise remain in authenticated server-session memory.
- Automated suites, startup sanity, diff checks, and human acceptance tests pass.
