# Agent Harness: User-bounded Read-only Investigation

## Current Contract

- MetaList owns orchestration; the HTTP route never asks an inference provider to
  search the namespace directly.
- Every chat request includes both the tab visible when Send was pressed and the
  tab that owns the investigative scope. Normally they are the same. A temporary
  Reference source view keeps the visible reference tab but retains the originating
  search tab as its scope. The server verifies the visible tab, then checks the
  originating tab's canonical search/sort/date state and resolves the actual members
  itself.
- The resolved `ScopedSearchSnapshot` is immutable and session-only. All later
  paging, tag refinement, exact-text refinement, backtracking, and source reopening
  are constrained to that snapshot.
- Only true matching nodes are evidence. Render-only ancestors may appear as
  contentless structural objects solely to preserve nesting; gray-bar content and
  tags never enter the agent context. `@password` content and tags are excluded
  before pages, facets, summaries, final evidence, or traces.
- Instructor owns all JSON/Pydantic calls. Final prose streams through the selected
  provider's native client. The supported providers are MetaList-managed Ollama and
  the OpenAI API; LiteLLM is not required by the current inference seam.
- No create, edit, move, tag, trash, delete, SQL, filesystem, or shell action is
  exposed.

## Runtime Flow

```text
POST /api2/ai/chat + required AgentScopeDescriptor
  → verify visible tab and originating scope tab's canonical state
  → AiChatSessionStore.start_turn
  → resolve selected inference provider
      → Ollama: ManagedOllamaRuntime.ensure_running + verify active context
      → OpenAI: resolve the server-side API key for this authenticated session
  → AgentRuntime.stream_scoped
      → freeze ScopedSearchSnapshot (S0)
      → Instructor route: respond | investigate_current_scope
      → respond: stream final prose without note evidence
      → investigate:
          activate scoped-investigation skill
          build first ordered note page + whole-subset tag facets
          → one page: Instructor selects directly relevant evidence IDs
                      rehydrate only those sources and stream final prose
          → multiple pages:
          Instructor InvestigationStep:
            replace WorkingSummary
            assess evidence sufficiency
            select one bounded action
          execute action with St ⊆ S0 assertions
          rebuild context with current page/state/summary only
          repeat (maximum 16 steps)
          rehydrate selected observed sources
          number root-deduplicated references and stream final prose
  → AiChatSessionStore.complete_turn
```

OpenAI requests use the selected supported model and reasoning effort, set
`store: false`, and keep the authorization header/API key out of trace wire bodies.
In password-protected namespaces the API key is encrypted with the namespace DEK
and stored in `app_settings`. In plaintext namespaces it is held only in server
memory under the authenticated session key: a browser refresh retains it, while
logout, lock/session replacement, or process restart removes it. The raw key is
never returned to the browser after configuration.

The high-level route sees the canonical conversation, the base system prompt, and
a trailing content-free `ROUTE_SELECTION_REQUEST` containing the exact current
request plus the user-driven search query, scope kind/label, sort/date state,
matching note/tree counts, and computed token-budgeted evidence-page count. Putting
the current request beside the routing instruction prevents an older note task from
being mistaken for the current follow-up. It
chooses `respond` for ordinary conversation/general knowledge and
`investigate_current_scope` only when the answer depends on saved-note evidence.
Corrections, objections, and challenges to the prior answer route to `respond`
unless they explicitly request fresh note evidence. Direct final-response payloads
repeat the exact current request, declare an empty reference catalog, and require a
short correction without adjacent topics or invented note citations.
Explicit requests to summarize, search, review, or otherwise use the user's saved
notes are bound into Instructor validation: `respond` is invalid and must retry as
`investigate_current_scope`. The route context never contains note content and does
not construct a global query.

The investigation call uses a flat, fully required `InvestigationStep` schema.
Inactive action arguments use explicit empty sentinels, avoiding root unions and
schema references that are unreliable with small local models. Static rules and
run-dependent rules are both bound into Pydantic validation: unavailable next
pages, out-of-range facet pages, undisclosed tags/state IDs, and unobserved source
IDs therefore participate in Instructor's visible retry rather than failing after
an apparently valid response.

Activity and trace labels omit a redundant counter on the initial structured
attempt. If validation or the provider fails and Instructor retries, the retry and
its validation labels explicitly show `attempt 2 of 2`; numeric attempt metadata
remains present in exact debug payloads for both attempts.

## Scope and Ordering

`app/services/agent/scope.py` freezes:

- normalized scope kind and label;
- canonical search/sort/date descriptor;
- eligible matching note IDs in visible hierarchy order;
- ordered result-tree roots;
- every ancestor path required to nest matching evidence inside its original tree;
- disclosure-safe plain text;
- exact tag-bar text and user tag terms in original order/spelling;
- locally assigned/inferred searchable tags, hierarchy IDs, and timestamps.

Supported frozen scope kinds are `search`, `all_notes`, and `untagged`; the wire
model retains `reference` compatibility for older clients. An empty normal search
is explicit `All notes`, not an absent/unbounded scope. Opening a Reference source
is navigation over the notes UI, not a new evidence boundary: subsequent chat turns
continue to capture the originating scope tab until the temporary view is dismissed.
Clicking another AI response reference replaces the active AI reference query in
that temporary tab. Following ordinary references from inside notes retains the
existing stacked navigation behavior.

Membership comes from the same `resolve_search_scope`, date filtering, untagged
membership, root sorting, `SearchIndex`, and `NoteStore` behavior as `/notes/view`.
`ResolvedViewScope` separates `matched_note_ids` from `allowed_note_ids`, so an
ancestor retained only to render a date/search match cannot become agent evidence.

The snapshot stores frozen records rather than live handles. Later edits or UI
navigation cannot change an in-flight run. The object becomes unreachable when the
stream finishes/cancels/fails; no run scope is written to SQLite or disk.

## Investigation State

`app/services/agent/investigation.py` owns one mutable run cursor over immutable
`S0`:

- current subset and disclosed state IDs;
- one-based result-tree page;
- one-based tag-facet page;
- observed source IDs;
- disclosed tag terms;
- refinement history for backtracking.

Every subset is asserted unique, ordered exactly as `S0`, and contained in `S0`.
Evidence pages serialize a `result_trees` array. Each entry is a root note object
whose descendants are recursively nested under `children`; the model never receives
a flat note list. Content-bearing nodes carry note IDs, content, timestamps, and
only their directly assigned raw `tags`; untagged nodes omit `tags`. Leaf nodes
omit `children`, and parent/root IDs are not repeated because nesting communicates
the hierarchy. Inherited, implied, and ontology-expanded tags are never included
or used for agent facets/refinements. Nonmatching or
protected ancestors required to preserve a path have `is_evidence: false` and carry
only an ID and nested children—never content, tags, or timestamps.
Refinements are cumulative; backtracking can restore only a state already disclosed
to the model.

### Note pages

- Pages greedily pack complete top-level result trees in frozen MetaList order to
  an approximate serialized-input-token target (default 5,000; configurable
  500–24,000), with a separate hard cap of 50 result trees by default
  (configurable 1–100). Tree counts therefore vary by page, and whichever bound is
  reached first starts the next page.
- A root tree is atomic and never crosses a page boundary. A single tree whose
  structure alone exceeds the target occupies its own page; content is reduced as
  far as possible without dropping its structural metadata.
- All matching nodes beneath selected roots retain frozen visible order.
- Each note returns bounded content (default 2,000 chars; 500–10,000), original
  content length, truncation state, exact user tags/tag bar, parent/root IDs, and
  ISO created/updated timestamps.
- Page cost includes the compact serialized JSON—not merely `content_text`—so IDs,
  tags, timestamps, hierarchy, keys, and punctuation consume the same budget.
- `token_estimation.py` provides one deterministic provider-neutral estimate for
  both page packing and debug feedback. It separately estimates ASCII word runs,
  numeric runs, punctuation/control whitespace, and UTF-8 non-ASCII sequences.
- Notes serialized on a page become observed and may later be reopened/cited.

### Tag facets

- Facets are computed across the entire current subset, never only the note page.
- Effective searchable tags follow normal MetaList inheritance/ontology/prefix
  semantics. Exact per-note tags remain separately visible.
- Each facet reports unique matching-note and matching-result-tree counts.
- Case-equivalent terms collapse deterministically.
- Ordering is descending note count, descending tree count, then tag text.
- Facet pages default to 50 tags and are configurable from 1–200.
- A tag refinement may reference only a term already disclosed by a facet or page
  note. Syntax uses existing MetaList tag grammar; no regex action exists.

### Action set

- `page_next`: advance when another ordered note page exists.
- `refine_tags`: narrow with disclosed tag terms and normal AND/OR/exclusion
  semantics.
- `refine_exact_text`: narrow by a bounded, case-insensitive literal substring.
- `inspect_tag_facets`: inspect another deterministic facet page.
- `backtrack`: restore a disclosed earlier subset.
- `reopen_sources`: rehydrate 1–12 previously observed frozen records.
- `answer`: declare sufficient evidence and select up to 12 observed source IDs for
  authoritative final rehydration.

## Bounded Working Context

When the frozen scope fits on one evidence page, the runtime bypasses
`WorkingSummary` but does not send the whole candidate page to the prose writer.
Instructor first returns a structured selection containing at most 12 exact IDs
from that page. The eye state is frozen when the user submits the turn: visible
diagnostics use `EvidenceSelection` with a required concise `reason`, while hidden
diagnostics use `EvidenceSelectionWithoutRationale`, whose only field is
`relevant_note_ids`. Dynamic Pydantic constraints reject invented or out-of-page IDs.
The current user's narrowest constraint—not the broader scope query—defines
relevance; sharing the scope topic while addressing a different subtopic or
mechanism is insufficient. The
runtime rehydrates only the selected frozen records and exposes only those records
and their ready-to-copy `[[UUID]]` citation tokens to final response generation.
This isolates relevance judgment in a small, inspectable structured call and makes
it impossible for final prose to drift into an unselected sibling. An empty
selection is valid when the candidate scope does not answer the question. For
multi-page investigation,
`WorkingSummary` is a complete replacement value on every step. It
contains source-backed facts, tentative conclusions, contradictions/uncertainties,
unresolved questions, and useful terms/tags. Each evidence entry carries its exact
source IDs; the runtime derives the deduplicated reference set from those structured
entries. Every evidence ID must be observed, and the serialized summary defaults to an
8,000-character budget configurable from 2,000–32,000.

`AgentContextBuilder.build_scoped_investigation_messages` reconstructs each call
from:

- base prompt and canonical conversation;
- active scoped-investigation skill;
- frozen scope metadata;
- current state/disclosed IDs and terms;
- current summary;
- current facet page;
- current note page or reopened sources.

Prior raw pages, earlier summary versions, and abandoned tool transcripts are not
appended. Agent Debug still records each exact wire request at the time it occurs.
Every generation has a response-type ceiling: 512 tokens for routes and one-page
evidence selection, 2,048 for multi-page investigation steps, and 1,024 for legacy
search-query preparation and final prose. Structured
requests carry `max_tokens`; native final-response streams carry
`options.num_predict`. Instructor partial streaming provides schema-aware parsing
while live activity reports an approximate output-token count. These limits prevent
malformed or repetitive output from generating without a practical bound.

On `answer`, `build_scoped_final_messages` receives the latest summary and newly
serialized frozen source records selected by the model. Final note claims must be
grounded in those authoritative records rather than the lossy summary. The runtime
places an exact `[[UUID]]` token beside each evidence source. The model must copy the
token from the same object whose content supports the claim; the final-response
prompt requires at least one direct token in every note-derived paragraph or list
item. The server validates the UUID against the current-run allowlist, assigns the
visible reference number, and renders a superscript marker. The visible References UI
groups cited children by root, but its hidden navigation query retains the exact
cited child UUIDs. Multiple cited children under one root use `UUID1 OR UUID2`, so
the existing search renderer preserves both ancestor paths and gray-redacts unrelated
sibling branches. An empty catalog produces no citations or References section.

Canonical conversation remains only user messages and completed assistant-visible
prose. Scope, skills, actions, summaries, pages, facets, traces, and citations are
transient working state and do not enter later conversation context.

## Prompt and Override Contract

- `prompts/system.md` contains only the read-only role, high-level route guidance,
  current-turn/history rules, citation contract, and Markdown/LaTeX/Mermaid output
  preference.
- `skills/scoped-investigation.md` contains investigation semantics, sufficiency
  guidance, action rules, tag grammar, paging/order hints, and summary/provenance
  requirements.
- `skills/select-relevant-evidence.md` contains the narrow one-page relevance
  contract. It is activated only for the structured `EvidenceSelection` call and
  is editable/restorable with the other skills.
- Namespace prompt/skill overrides are frozen at run start and editable through
  `Agent prompts…`.
- The nested scoped skill uses versioned key
  `pref.ai.skill.scoped_investigation_v5`; one-page relevance selection uses
  `pref.ai.skill.select_relevant_evidence_v1`. Saved verbose-payload v4,
  inherited-tag v3, flat-page
  `pref.ai.skill.scoped_investigation_v2`, and legacy
  `pref.ai.skill.search_notes` overrides are preserved but never applied. The
  editor displays an explicit incompatibility notice; Save or Restore removes
  them atomically.

## UI and Debug

- A persistent scope chip remains visible on the assistant turn even when the
  developer eye toggle is off: for example,
  `Scope · project-foo · 834 notes in 217 result trees · 9 evidence pages`.
- Eye mode retains in-place lifecycle panels for scope freezing, model calls,
  evidence pages, one-page relevance selection, summary/action selection,
  refinements, facets, source reopening, and final writing. Each panel carries a
  separate approximate input-token count.
- Hidden eye mode still shows one compact live Working indicator without exposing
  refinement/search details.
- Agent Debug records frozen scope/counts, every exact provider request/response and
  retry, every full summary replacement, action arguments/reason, state transition,
  page/tool payload, source rehydration, timing, error, and final response. Every
  investigation request gets a dedicated evidence-payload event containing the
  exact compact note-page JSON sent to the model. Copy all writes the complete
  latest-run trace as formatted JSON for bug reports.
- Debug is latest-run session memory only. Clear/logout/lock/restart behavior is
  unchanged; nothing is persisted.
- Stop and Clear Chat abort the active browser/server stream, which cancels pending
  Instructor/provider work and releases run-local state.

## Main Files

- API: `app/api/routes/ai.py`
- Runtime: `app/services/agent/runtime.py`
- Scope freeze: `app/services/agent/scope.py`
- Investigation state/actions: `app/services/agent/investigation.py`,
  `app/services/agent/actions.py`
- Context: `app/services/agent/context.py`
- Settings: `app/services/agent/retrieval_settings.py`
- Prompts/skills: `app/services/agent/prompts/`, `app/services/agent/skills/`,
  `app/services/agent/skill_settings.py`
- Inference/debug: `app/services/agent/inference.py`,
  `app/services/agent/ollama_inference.py`,
  `app/services/agent/openai_inference.py`, `app/services/agent/trace.py`
- OpenAI credentials: `app/services/openai_credentials.py`
- Scope UI: `app/static/js/modules/ai-chat/ai-chat-panel-controller.js`
- Settings/prompt UI: `app/static/js/modules/modals/ai-agent-settings-modal.js`,
  `app/static/js/modules/modals/agent-prompt-editor-modal.js`

## Deferred Seams

- LiteLLM may wrap the provider-neutral inference seam if routing, fallbacks, or
  cost accounting later justify the dependency.
- Regex refinement requires a separate safe-engine/time/budget design.
- Any note mutation requires new closed actions, permissions, confirmation UX, and
  tests; it must not be added by widening this read-only loop.
