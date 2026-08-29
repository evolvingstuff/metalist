# AI Chat and Scoped Read-only Agent

## Scope

- MetaList chats with one user-selected Ollama model through an authenticated,
  application-owned agent runtime.
- Every Send freezes the currently displayed MetaList result scope. The agent can
  investigate only matching notes inside that boundary; it cannot run a new
  namespace-wide search or escape to hidden notes.
- The runtime is read-only. It cannot create, edit, move, tag, trash, or delete
  notes.
- Instructor owns structured route/investigation calls. Final natural-language
  prose streams directly from Ollama. LiteLLM and remote providers are deferred.
- While Ollama generates, the active eye-mode panel shows an approximate output-token
  count that updates in place with a subtle pulse; completed panels retain the final
  count separately from their input estimate.
- Every generation is bounded over the wire: route selection uses 512 output tokens;
  multi-page investigation steps use 2,048; query and final-response requests use
  1,024.

## Scope at Send

The browser captures one required view descriptor from the active tab:

- normal search, All notes, Untagged notes, or temporary Reference source;
- executed search text;
- sort mode and date filter;
- reference UUIDs where applicable;
- a human-readable scope label.

The server verifies that the descriptor targets the active tab and matches its
canonical search/sort/date state, then resolves actual note membership itself.
The browser never submits a trusted corpus-sized UUID list. Later typing, tab
switches, or reference navigation do not change the running request.

The assistant turn shows a persistent scope chip such as:

```text
Scope · project-foo · 834 notes in 217 result trees · 9 evidence pages
```

An empty search is explicitly `Scope · All notes`. The chip remains visible when
developer diagnostics are hidden.

The same total is supplied to the route-selection model before note content is
loaded; every evidence panel reports `page N of M` thereafter.

Only true matching nodes become evidence. Ancestors needed to make the result tree
readable appear only as contentless structural objects. Gray/redacted and protected
`@password` content and tags are excluded entirely.

## Investigation Behavior

The first structured call chooses:

- `respond` for ordinary conversation/general knowledge that does not require the
  user's saved notes;
- `investigate_current_scope` when the answer depends on evidence in the frozen
  result view.

The routing request also receives a content-free `ACTIVE_METALIST_SCOPE` block
with the exact active user search query, scope label/kind, sort/date state, and
result counts. Explicit saved-note requests cannot validate as a direct `respond`.
Note content enters the model context only after investigation is selected.

An investigation begins with the first ordered page of matching result trees plus
a ranked tag-facet page covering the whole current subset. If that page is the
complete scope, a small structured Instructor call selects only the exact note IDs
that directly answer the current user question. MetaList rehydrates only those
sources for final response generation; it does not create a redundant rolling
summary, and the prose writer never receives unselected candidate notes. Multi-page
investigations use subsequent Instructor calls to replace a
bounded working summary and choose exactly one action: page next, tag refinement,
exact-text refinement, inspect more tag facets, backtrack, reopen observed sources,
or answer.

Raw prior pages are removed from the next model context. Only the current page,
current state/facets, replacement summary, and any requested source reopens remain.
Before answering, MetaList rehydrates the selected frozen source records, so final
wording is based on authoritative note content rather than summary memory.

The agent cannot:

- use a tag it has not seen in a facet or exact per-note tag list;
- reopen or cite an unobserved note ID;
- request a page/facet/state that does not exist;
- refine outside the frozen original scope;
- use regex in this release.

Those rules are validated programmatically inside the Instructor retry boundary,
not left to prompt compliance.

## Ordering, Pages, and Facets

- Note pages use MetaList's canonical top-level result-tree order and visible node
  order. SearchIndex membership never becomes ordering.
- Results near the top are generally newer or more highly user-ranked, which is a
  prioritization hint rather than relevance proof.
- Evidence pages greedily pack complete result trees, in canonical order, to an
  approximate serialized-input-token target. The default is 5,000 tokens and the
  configurable range is 500–24,000; page 1 may therefore contain many more roots
  than page 2 when page 2's roots are longer.
- A separate hard cap allows at most 50 result trees per evidence page by default
  (configurable from 1–100). Whichever limit is reached first starts the next page.
- A root tree is never divided between pages. An individually oversized tree gets
  a page of its own and its note content is reduced toward the target without
  dropping hierarchy metadata.
- Each matching note returns at most 2,000 content characters by default (range
  500–10,000). This is a separate per-note guard, not the page-size mechanism.
- The estimate covers compact serialized JSON, including content, UUIDs, tags,
  timestamps, hierarchy, object keys, and punctuation. The same deterministic
  estimator drives the debug-panel token estimates.
- Each page is a `result_trees` array of root note objects with recursively nested
  `children`, not a flat note list. Content-bearing nodes expose note IDs, content,
  created/updated timestamps, and directly assigned raw tags in tag-bar order.
  Untagged notes omit `tags`; leaf notes omit `children`; parent/root IDs are not
  repeated because nesting already communicates the hierarchy. Truncation metadata
  appears only when content is actually truncated.
  Contentless `is_evidence: false` ancestors preserve paths to nested matches
  without disclosing gray/redacted note information.
- Ranked facets cover the whole current subset and report both matching-note and
  matching-result-tree counts. Default facet page size is 50 tags (range 1–200).
- Facets and agent tag refinements use directly assigned raw tags only. They do not
  use inherited, implied, or ontology-expanded tags.
- The replacement working summary defaults to 8,000 characters (range
  2,000–32,000) and must retain observed-source provenance.

The five active limits are namespace-scoped controls in `AI Agent Settings…`:
per-note characters, approximate evidence-page tokens, result trees per evidence
page, ranked facets per page, and working-summary characters.

## Configuration and Managed Ollama

- Open `AI Agent Settings…` from the command palette or chat gear to select an
  installed model, download a named model, and edit investigation budgets.
- The compact composer controls choose model and Thinking Off/Low/Medium/High.
  Selection persists immediately; GPT-OSS does not offer Thinking Off.
- MetaList lazily starts one owned Ollama daemon shared by namespaces at
  `127.0.0.1:11435` with `OLLAMA_CONTEXT_LENGTH=32768`, cloud/history/request-body
  logging disabled, and one parallel request.
- Runtime ownership is coordinated through
  `~/MetaList/runtime/ollama/ollama-runtime.json`; the bounded log is
  `~/MetaList/logs/ollama-managed.log`.
- Every run preloads the selected model, checks `/api/show` and `/api/ps`, records
  maximum/loaded/required context in Agent Debug, and refuses an undersized active
  allocation.

Open `Agent prompts…` to inspect/override packaged prompt Markdown and registered
skills. Skills are collapsed with a disclosure arrow and trigger label. Overrides
are encrypted namespace preferences where applicable and affect the next run.
`Restore packaged defaults` removes all overrides. If the old Search-skill override
exists, the editor shows an explicit incompatible-contract notice; it is preserved
but never applied until Save or Restore removes it.

## Panel and Cancellation

- `Show/Hide AI Chat` is available in the command palette and notes-view context
  menu. Chat and the right-side activity calendar are mutually exclusive.
- Chat starts at one third of the viewport and narrows the notes area. Dragging its
  separator persists width while retaining at least 280 px for chat and 480 px for
  notes. Composer height also persists.
- The header contains a default-off developer eye toggle, Agent Debug, Clear,
  settings, and close. Eye visibility is namespace-scoped and survives restart.
- With eye mode hidden, an active request still shows one compact Working indicator
  with phase and elapsed time. With eye mode visible, tinted panels report scope,
  model attempts/retries, selected action and reason, pages, refinements, facets,
  source reopens, and response writing. Logical start/completion events update one
  panel; retries remain separate. Every panel includes approximate input tokens;
  model-generation panels also show approximate output tokens as chunks arrive.
  Every panel shows its own retained duration; the current panel counts live and
  completed durations remain visible after reopening the chat.
- The composer remains editable during generation. Send becomes red Stop and aborts
  browser/server Ollama work. Clear Chat cancels and awaits any active request before
  clearing transcript and latest trace. No status/error line is placed below the
  composer.
- A Thinking disclosure appears only if the model emits real reasoning; Thinking
  Off never shows a fake heading.

## Rendering and References

- Assistant output is rendered as Markdown during streaming. Completed LaTeX and
  fenced Mermaid are supported. Blank lines between ordered-list items produce one
  loose list rather than restarting numbering. Explicit non-one list starts are
  honored, and repeated model-generated section markers are normalized to sequential
  numbering.
- The final model receives exact evidence-note sources with a ready-to-copy
  `[[UUID]]` token beside each source. Every note-derived paragraph or list item is
  prompted to copy the token from the same evidence object that supports its claim.
  Invented, stale, unobserved, and prior-turn references are stripped; the server
  assigns the visible reference numbers programmatically. Tokens are written
  directly after claims without model-generated `Note ID`/`Source` labels.
  Standalone model-generated source bullets and links are removed programmatically;
  any valid citation token on that line is retained on the preceding claim.
- While a response streams, an incomplete trailing `[[UUID]]` token is withheld
  until both closing brackets arrive. It therefore appears atomically as the final
  numbered citation instead of briefly rendering as a note-title mention.
- Inline markers render as clickable superscript `[1]` links. A separate References
  section contains preview-labeled links deduplicated by top-level result tree;
  `Open all references` is available for multiple roots.
- Root deduplication is presentational only. Each reference retains the exact cited
  child UUIDs as its hidden navigation query. If multiple cited children share a
  root, the query is `UUID1 OR UUID2`; normal search behavior preserves both paths
  and gray-redacts unrelated siblings.
- Individual/all-reference navigation uses the temporary Reference source context,
  leaves the visible search field empty, and provides the dismissible X to return
  to the prior tab context.
- Common UUID dash substitutions are normalized programmatically. UUIDs in fenced
  code/existing links remain literal.
- Right-click a completed answer and choose `Copy Response` to copy Markdown tagged
  `@markdown @llm` into the MetaList note clipboard and rich/plain content onto the
  system clipboard.

## Session and Debug Boundaries

- Transcript/activity state lives only in server memory keyed by authenticated
  session token hash. Refresh rehydrates it; logout, auth reset, runtime lock, or
  restart clears it.
- Canonical future context includes only user text and completed assistant prose.
  Scope, skills, summaries, facets, pages, actions, tool payloads, reasoning, and
  citations are transient.
- The latest debug trace is always captured so Agent Debug can be opened after a
  failure. Starting another run replaces it.
- Exact detail is shown by default and may be toggled after a run without changing
  capture. The outline records every exact outbound Ollama body and response,
  retry/validation state, frozen scope/counts, summary replacement, action reason,
  state transition, bounded evidence payload, source rehydration, timing, and final
  response.
- Every investigation request has an `Evidence payload sent to Ollama` entry with
  the exact compact note tree for that request. `Copy all` copies the complete
  current/most-recent run—including all events and payloads—as formatted JSON.
- Traces are never stored in SQLite, files, browser storage, or canonical history.

See `docs/design/agent-harness.md` for service and invariant details.
