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
  tags never enter the agent context. `@password` notes and their complete
  descendant subtrees are excluded before counts, pages, facets, summaries, final
  evidence, or traces for every provider.
- A single namespace-level cloud privacy policy applies to OpenAI and future cloud
  providers while local Ollama ignores its configurable lists. The policy supports
  tag/text whitelists and blacklists; entries within each side are OR, a blacklist
  match wins, and an empty whitelist admits notes not blacklisted. Tag rules use the
  same inherited, implied, and synonym-expanded effective tags as canonical search.
  Phrase rules are case-insensitive literal substrings. A directly hidden ancestor
  hides its entire subtree, so a descendant can never be disclosed without its path.
- Instructor owns all JSON/Pydantic calls. Final prose streams through the selected
  provider's native client. The supported providers are MetaList-managed Ollama and
  the OpenAI API; LiteLLM is not required by the current inference seam.
- No create, edit, move, tag, trash, delete, SQL, filesystem, or shell action is
  exposed.

## Runtime Flow

```text
POST /api2/ai/chat + required AgentScopeDescriptor
  → verify visible tab and originating scope tab's canonical state
  → apply the provider disclosure boundary and prune hidden subtrees
  → freeze the already-filtered ScopedSearchSnapshot (S0)
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
          → one page: send the complete raw nested result-tree page directly to
                      final prose generation
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
and matching note/tree counts. It does not size or serialize note evidence merely
to choose a route. Putting
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

## Cloud Privacy Policy

`app/services/agent/cloud_privacy.py` resolves the shared policy from encrypted
namespace client preferences where namespace encryption is enabled. It evaluates
each candidate and every canonical ancestor before `ScopedSearchSnapshot` is built.
Consequently hidden notes cannot influence scope counts, evidence serialization,
facets, narrowing, citations, provider prompts, or Agent Debug payloads.

The four ordered policy lists are whitelisted tags, whitelisted plaintext phrases,
blacklisted tags, and blacklisted plaintext phrases. Matching is case-insensitive.
Tag evaluation reads `SearchIndex.list_effective_tag_terms_for_note`, so ancestor
inheritance and ontology implications/synonyms have exactly the same meaning as in
search. Text evaluation uses the note's disclosure-safe plain text. The
non-overridable `@password` rule remains active for local and cloud providers.

`POST /api2/ai/cloud-privacy/preview` applies the same server evaluator to visible
note IDs. While the pointer is over the chat column, the browser gives every hidden
note in the current view a readable gray background; it does not replace content
with search-redaction bars. This preview is explanatory only—the frozen-scope filter
is the security boundary.

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
  a provider-specific approximate serialized-input-token target (Ollama default
  5,000, configurable 500–24,000; OpenAI default 250,000, configurable
  500–250,000),
  with a separate provider-specific hard cap of 50 result trees by default
  (configurable 1–100). Tree counts therefore vary by page, and whichever bound is
  reached first starts the next page.
- A root tree is atomic and never crosses a page boundary. A single tree whose
  structure alone exceeds the target occupies its own page; content is reduced as
  far as possible without dropping its structural metadata.
- All matching nodes beneath selected roots retain frozen visible order.
- Each note returns bounded content (default 2,000 chars; 500–10,000), original
  content length, truncation state, exact user tags/tag bar, parent/root IDs, and
  ISO created/updated timestamps.
- All retrieval limits are stored independently for Ollama and OpenAI. Selecting a
  provider resolves only that provider's settings; changing OpenAI page sizing can
  never alter the Ollama configuration, or vice versa.
- Persisted values equal to the former OpenAI defaults (24,000 page tokens and
  48,000 narrowing tokens) resolve to the new 250,000/500,000 defaults; all other
  custom values remain unchanged.
- Page cost includes the compact serialized JSON—not merely `content_text`—so IDs,
  tags, timestamps, hierarchy, keys, and punctuation consume the same budget.
- `token_estimation.py` provides one deterministic provider-neutral estimate for
  both page packing and debug feedback. It separately estimates ASCII word runs,
  numeric runs, punctuation/control whitespace, and UTF-8 non-ASCII sequences.
- Notes serialized on a page become observed and may later be reopened/cited.

### Tag facets

- Facets are computed across the entire current subset, never only the note page.
- Facets enumerate directly assigned raw tags. Ontology-equivalent spellings are
  attached as explicit synonym metadata (for example `ML3 = MetaList`) so the
  model can understand meaning without receiving inherited or implied tags.
- Each facet reports unique matching-note and matching-result-tree counts.
- Case-equivalent terms collapse deterministically.
- Ordering is descending note count, descending tree count, then tag text.
- Facet pages default to 50 tags and are configurable from 1–200.
- A tag refinement may reference only a term already disclosed by a facet or page
  note. Syntax uses existing MetaList tag grammar; no regex action exists.

### Current one-page overflow experiment

The active overflow strategy is deliberately simple for evaluation. After the
route selects `investigate_current_scope`, MetaList walks the deterministic root
order and retains the longest complete-root prefix whose serialized evidence cost
does not exceed the provider's evidence-page token target. This experiment ignores
the separate result-tree-count cap, so OpenAI can approach its 250,000-token page
target instead of stopping after 50 roots. It removes all later root trees from the
run-local subset, never splits a root tree, never changes root order, and never
escapes the frozen user scope. The retained raw nested page then goes directly to
final generation. The final prompt states that later roots were intentionally
omitted, supplies exact included/omitted note and result-tree counts, and forbids
claiming exhaustive scope coverage.

This sizing is lazy. Startup, normal note interaction, view snapshots, the search
header, and content-free route selection do not tokenize result trees. Only an
`investigate_current_scope` run enters the prefix walk. Root costs are evaluated in
order, and the walk stops immediately after the first root that would overflow the
page; no later roots are tokenized. The retained roots reuse the lazy serialized
root-cost cache when the final bounded page is built.

Developer-eye activity reports original versus retained note/tree counts, the
number of trailing trees and notes omitted, and the retained serialized-token estimate.
Agent Debug stores the exact retained and omitted root UUID lists in session-only
trace state.

The tag-narrowing and rolling multi-page implementation below remains intact as a
separate internal overflow mode so this experiment can be reversed without
reconstructing that machinery.

### Legacy multipage automatic context narrowing (retained)

After route selection chooses `investigate_current_scope`, MetaList estimates the
full serialized-token cost of the frozen subset before exposing a raw evidence
page. If that cost exceeds the provider-specific ideal narrowed-scope target, the
`narrow_context_v1` skill receives the exact current request, immutable user search
boundary, ranked raw-tag facets with effective inherited-match note/tree counts,
and synonym relationships. Tags already positively required by every OR branch
of the user search are reported as existing constraints and excluded from the
candidate facets, so the model cannot propose a redundant constraint such as
`ML3` for an `ML3 -journal` scope. Formatting/meta tags beginning with `@` are
also excluded because they do not express semantic evidence relevance. Ontology
keys differing only by case contribute a merged synonym set because MetaList tag
matching is case-insensitive; this never expands the plan's legal output values,
which remain the exact raw tags listed in the frozen-context facets. Per-run
case-folded ontology equivalence lookups are cached, so facet construction does
not rescan the entire ontology for every candidate-tag/note comparison. Facet
counts are aggregated once per unique inherited raw tag instead of rescanning
every note for every candidate. Full-scope sizing and facet construction run
outside the async server loop while a live automatic-narrowing status remains
visible and cancellation-responsive.
Defaults are 10,000 approximate tokens for Ollama and 500,000 for OpenAI—two
default evidence pages for each provider. Ollama is configurable from
1,000–200,000; OpenAI is configurable from 1,000–500,000.

The model returns only an ordered list of disclosed raw tags. The prompt asks it
to aim for up to three candidates, capped by the eligible semantic-tag count, so
MetaList can measure useful alternatives instead of receiving an unnecessarily
short plan. This is guidance rather than schema enforcement: a one-tag plan is
always valid. MetaList tests the
prefixes cumulatively as AND constraints (`tag-a`, then `tag-a tag-b`, and so on)
inside the current frozen subset. It measures every proposed prefix until one
produces zero results, rejects that zero-result prefix, and selects the first
non-empty candidate at or below the
configured token target. Because cumulative AND prefixes can only shrink, that
candidate is the closest one below the target. If every proposed prefix remains
above target, MetaList retains the smallest non-empty result reached. Only the
selected candidate becomes a new investigation state, and every state remains a
server-asserted subset of `S0`; model output can therefore never broaden the user
search.

Narrowing uses normal raw-tag inheritance paths. If `A` contains sibling children
`B` and `C`, and `C` contains `D`, requiring a tag on `C` retains evidence `C` and
`D`, renders structural ancestor `A`, and removes unrelated sibling `B`. Requiring
tags found only on sibling branches `B` and `C` yields zero because no single
note-to-ancestor path satisfies both constraints. Narrowing never drops a
matching note's descendants or structural ancestors.

The first experiment intentionally uses raw tags only. A future facet source may
add clearly distinguished LLM-assigned "ghost tags" for broader coverage. A
separate future soft-ranking phase may award root-note trees points for matching
suggested phrases without excluding trees that lack those phrases; neither
extension may escape `S0`.

Developer-eye activity shows the original and target sizes, the complete ordered
tag list proposed by the model, every tested cumulative prefix with resulting
note/tree/token counts, rejected zero-result prefixes, and the selected final
expression. Agent Debug retains the exact model request and response plus the
complete programmatic evaluation table as copyable session-only trace data.

### Action set

- `page_next`: advance when another ordered note page exists.
- `refine_tags`: narrow with disclosed tag terms and normal AND/OR/exclusion
  semantics.
- `refine_exact_text`: narrow by a bounded, case-insensitive literal substring.
- `inspect_tag_facets`: inspect another deterministic facet page.
- `backtrack`: restore a disclosed earlier subset.
- `reopen_sources`: rehydrate 1–12 previously observed frozen records.
- `answer`: declare sufficient evidence. MetaList then rehydrates the 32
  highest-rated accumulated note IDs as final-answer candidates.

## Bounded Working Context

When the active run-local scope fits on one evidence page, the runtime bypasses
`WorkingSummary` and sends that complete raw page of recursively nested result
trees directly to final prose generation. Every evidence object carries its own
ready-to-copy `[[UUID]]` citation token, and every evidence ID on the page is an
allowlisted candidate citation. The final writer must apply the current user's
exact request as the relevance constraint and omit unrelated candidate nodes; the
server still validates every emitted citation against the frozen page. Under the
current overflow experiment, this same direct path receives the retained leading
root-tree prefix and is explicitly told that it is not exhaustive.

For multi-page investigation, each decision receives the raw current page without
the accumulated ratings from earlier pages. It returns only applicable current-page
note IDs and an integer importance score from 1–100. This prevents scores for a new
page from being anchored by earlier ratings. MetaList merges pages
programmatically, deduplicates IDs using their highest score, sorts them by score,
and retains the best 64. Every rated ID must occur on the current page, and the
serialized ratings default to an 8,000-character budget configurable from
2,000–32,000.

`AgentContextBuilder.build_scoped_investigation_messages` reconstructs each call
from:

- base prompt and canonical conversation;
- active scoped-investigation skill;
- frozen scope metadata;
- current state/disclosed IDs and terms;
- current facet page;
- current note page or reopened sources.

Prior raw pages, accumulated ratings, earlier summary versions, and abandoned tool
transcripts are not appended. Agent Debug still records each exact wire request at
the time it occurs.
Every generation has a response-type ceiling: 512 tokens for routes, 2,048 for
multi-page investigation steps, and 1,024 for legacy search-query preparation.
Final prose is provider-specific: 1,024 tokens for Ollama and 8,192 for OpenAI.
Structured requests carry their provider's output-token option; native
final-response streams carry `options.num_predict` for Ollama or
`max_completion_tokens` for OpenAI. OpenAI `finish_reason="length"` is a provider
failure and can never be recorded as a completed partial answer. Instructor partial
streaming provides schema-aware parsing while live activity reports an approximate
output-token count. These limits prevent malformed or repetitive output from
generating without a practical bound.

On `answer`, `build_scoped_final_messages` receives the accumulated rankings and
newly serialized frozen source records for the 32 highest-rated candidates. Final
note claims must be grounded in those authoritative records rather than the lossy
rankings. The final writer may use and cite any supporting subset of the 32; unused
candidates must not become citations or References entries. The runtime
places an exact `[[UUID]]` token beside each evidence source. The model must copy the
token from the same object whose content supports the claim; the final-response
prompt requires at least one direct token in every note-derived paragraph or list
item. The server validates the UUID against the current-run allowlist, assigns the
visible reference number, and renders a superscript marker. The visible References UI
groups cited children by root, but its hidden navigation query retains the exact
cited child UUIDs. Multiple cited children under one root use `UUID1 OR UUID2`, so
the existing search renderer preserves both ancestor paths and gray-redacts unrelated
sibling branches. An empty catalog produces no citations or References section.
During streaming, reference UI is withheld. Completed References render as a
collapsed disclosure, and the transcript reveals only its heading at the bottom of
the viewport until the user expands it.

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
- Namespace prompt/skill overrides are frozen at run start and editable through
  `Agent prompts…`.
- The nested scoped skill uses versioned key
  `pref.ai.skill.scoped_investigation_v6`. Saved prose-summary v5, verbose-payload v4,
  inherited-tag v3, flat-page
  `pref.ai.skill.scoped_investigation_v2`, and legacy
  `pref.ai.skill.search_notes` overrides are preserved but never applied. The
  editor displays an explicit incompatibility notice; Save or Restore removes
  them atomically.

## UI and Debug

- The assistant response does not carry a persistent scope chip. Eye mode exposes
  the frozen scope label and counts through its lifecycle panels.
- Eye mode retains in-place lifecycle panels for scope freezing, model calls,
  evidence pages, direct one-page generation, summary/action selection,
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
- Cloud privacy: `app/services/agent/cloud_privacy.py`
- Scope UI: `app/static/js/modules/ai-chat/ai-chat-panel-controller.js`
- Settings/prompt UI: `app/static/js/modules/modals/ai-agent-settings-modal.js`,
  `app/static/js/modules/modals/agent-prompt-editor-modal.js`

## Deferred Seams

- LiteLLM may wrap the provider-neutral inference seam if routing, fallbacks, or
  cost accounting later justify the dependency.
- Regex refinement requires a separate safe-engine/time/budget design.
- Any note mutation requires new closed actions, permissions, confirmation UX, and
  tests; it must not be added by widening this read-only loop.
