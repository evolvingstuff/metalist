# Agent Harness: Single-Payload Read-only Investigation

## Contract

MetaList owns orchestration and evidence access. The selected model can either
answer normally or investigate the exact result scope visible when the user pressed
Send. Investigation cannot search outside that boundary or mutate notes. Explicit tag proposal requests use a separate application-owned bulk operation described below.

The supported provider is the OpenAI API. Instructor owns
the small structured routing call; final prose streams through the provider's native
client. LiteLLM is not part of the current path.

## Runtime Flow

```text
POST /api2/ai/chat + AgentScopeDescriptor
  → verify the visible tab and originating scope tab
  → resolve canonical search/sort/date membership server-side
  → apply the provider disclosure boundary
  → freeze immutable ScopedSearchSnapshot S0
  → select provider and verify its runtime/credential
  → Instructor route: respond | investigate_current_scope | tag_proposals | metalist_help
      respond:
        stream final prose, including the selected note when available
      investigate_current_scope:
        activate scoped-investigation skill
        walk complete root trees in canonical order
        retain the longest leading prefix within the provider token limit
        serialize one full nested evidence payload
        stream the final answer directly from that payload
  → complete the in-memory chat turn
```

There is no paging cursor, next-page decision, working summary, source-ranking
memory, facet browser, or automatic tag narrowing. A request gets at most one
evidence payload.

## Conversation disclosure boundaries

The display transcript stays visible when the provider or disclosure boundary
changes. Model-visible history starts fresh at that boundary. The server hashes
the provider, configured privacy policy, and the namespace-wide set of permitted
note IDs before each turn. A policy edit, newly applied/inherited `@password`
restriction, changed ontology/content match, or removal of previously permitted
notes invalidates prior history. Unknown history provenance is excluded
conservatively. Both route selection and final generation consume this filtered
history, including when the current evidence scope is empty. Returning to an old
provider does not automatically restore its previous context.

Citation removal alone does not sanitize answer prose. This boundary prevents
automatic reuse of earlier note-derived answers; text the user deliberately types
or pastes into the new message is still sent to the selected provider. It cannot
recall information already sent in an earlier request.

## Scope and Ordering

`app/services/agent/scope.py` freezes:

- normalized scope kind and label;
- canonical search, sort, and date descriptor;
- matching note IDs in visible hierarchy order;
- ordered result-tree roots and structural ancestor paths;
- disclosure-safe note content, directly assigned raw tags, direct unresolved tag proposals, and timestamps.

Supported scope kinds are Search, All notes, and Untagged notes. A temporary AI
Reference source keeps the originating search as the evidence boundary for later
questions. Clicking another AI reference replaces that temporary reference query;
ordinary references followed inside notes retain their separate stacked navigation
behavior.

Chat interactions preserve the current edit session. Send first saves the latest
draft without deselecting it, then supplies a required `selected_note_id` (empty
when no note is selected). After checking authoritative visible-view membership,
the server freezes the permitted portions of the containing top-level tree:
ancestors, siblings, and descendants, including collapsed notes. Search-redacted
branches are excluded using the server's visible-view membership, even if a user
has temporarily revealed or selected them for editing. Blacklisted and password
branches are independently excluded. Each permitted node carries its complete
text, direct tags, parent ID, and an `is_selected` marker identifying the edited
node. Unrelated top-level trees are not added through selection. The same disclosure
policy removes private branches before serialization, token sizing, or citations.
Shared agent text extraction also includes already-cached URL titles alongside
their URLs, labeled as metadata rather than fetched page content. This applies to
selected trees, broader investigation, and tagging inputs. It reads only the
in-memory successful-title cache after note disclosure filtering; it never starts
a URL fetch, rewrites stored notes, or attaches titles from excluded notes. Titles
are frozen with the note text and counted in the evidence budget. A title on a
parent URL remains associated with that parent for citations.
A note selected in a temporary reference view is checked against that visible
view; its containing tree is supplied separately without replacing the originating
search scope. The whole selected tree counts toward the evidence token budget;
an oversized tree fails visibly before provider calls rather than being clipped.

`SELECTED_NOTE_CONTEXT` accompanies routing and final generation. The model uses
selection, conversation, and the request together to infer the intended target;
there is no keyword or singular/plural routing rule. `has_selection` distinguishes
no selection from a selected but unavailable note. Unavailable selections expose
only status, selection presence, and a reason: blacklisted, not whitelisted,
password protected, search redacted, or not found. Restrictions inherited from
ancestors also apply; reasons never expose the matching rule, note ID, tags, or
content. The AI explains the restriction without suggesting reselection or pasting
blocked content as a workaround. Each Send replaces prior selection
context. This adds no note editing or child-creation capability.

For broader search investigation, only true matches are evidence. An ancestor
retained solely to preserve a search path is a contentless structural object.
The separately supplied selected tree can include nonmatching ancestors retained
as visible search context, but never search-redacted relatives. Both search and
privacy restrictions apply before content, tags, or citation IDs are serialized.
The snapshot stores frozen records, not live note handles, so edits and navigation
cannot alter an in-flight request.

## Disclosure Boundary

`@password` notes and their complete descendant subtrees are always excluded.

Cloud providers additionally share one namespace-level policy with tag/text
whitelists and blacklists. Entries on each side are OR; blacklist wins. Tag rules
use canonical inherited, implied, and synonym-expanded effective tags. Text rules
are case-insensitive literal substrings. A hidden ancestor hides every descendant.

Filtering happens before counts, token sizing, serialization, citations, or Agent
Debug. The hover preview calls the same evaluator and gives hidden notes a readable
gray background; the preview is explanatory, while server filtering is the security
boundary.

## One Evidence Payload

`app/services/agent/investigation.py` performs one lazy ordered prefix walk after
the route chooses `investigate_current_scope`:

1. Serialize and estimate each complete root tree in canonical order.
2. Retain it if the cumulative estimate remains within the provider limit.
3. Stop before the first root that would overflow.
4. Omit that root and every following root.
5. Fail visibly if the first complete root alone exceeds the limit.

A root is atomic and never split. Retained notes contain their full disclosure-safe
content; there is no per-note character limit or truncation metadata. Token sizing
is not performed during startup, normal note interaction, route selection, or search
rendering.

The payload is a `result_trees` array. Each root is a JSON object with recursively
nested `children`. Evidence nodes contain `note_id`, `content_text`, created/updated
timestamps, directly assigned raw `tags` when present, and direct `proposed_tags`
when present. Proposed tags remain separate from accepted tags; inherited and
ontology-expanded terms are not serialized as stored sources. Leaf nodes omit
`children`; nesting communicates parent/root relationships.
Contentless structural ancestors contain only their ID, `is_evidence: false`, and
the retained child path.

The final request includes exact original/included/omitted note and root counts. If
anything was omitted, the model is told not to claim exhaustive scope coverage.
The current user request, rather than the broad search topic, defines relevance.

## Configuration

The only retrieval setting is a provider-specific maximum approximate evidence
token count:

- OpenAI default 500,000; allowed 500–500,000.

The deterministic estimator covers the serialized JSON, not just note text. The
same estimate is used for retention and developer feedback.

Old preferences for maximum note characters, character-sized pages, roots per
page, ranked tags per facet, working-summary characters, and ideal narrowed-scope
tokens are obsolete. They are ignored and removed during normal preference writes.

## Routing and Prompts

The route sees canonical conversation history, the disclosure-safe selected tree
when available, and a content-free block containing
the exact current user request, user search, scope kind/label, sort/date state, and
note/root counts. It does not serialize the broader result content to choose a route.

`respond` is for conversation or answers supported by the supplied selected tree.
Every supplied tree node is an allowed citation source; answers cite the actual
supporting child, sibling, or ancestor. The model
interprets the request and conversation to choose investigation or a tag operation.
Instructor validates supported action names, required fields, and field types;
no keyword classifier, prompt signal, or rationale-text heuristic overrides the
model decision. Execution still enforces permissions, scope, and tool limits.
Selected-note evidence must fit the configured evidence token limit before any
provider request; broader investigation reserves that cost before retaining its
root prefix. Selection remains available even when its root is beyond that prefix.
Action regression expectations measure whether the selected action was appropriate.

The packaged scoped skill describes one authoritative payload and direct final
answer. No skill or prompt describes page traversal, summary mutation, facet
selection, or context narrowing.

## Citations and References

Evidence note IDs are valid citation sources. The model cites a supporting claim by
copying `[[UUID]]` from the same note object whose `content_text` supports it. The
server rejects invented, stale, prior-turn, or undisclosed UUIDs, deduplicates
repeated adjacent citations, orders citation groups numerically, and renders
clickable superscript numbers.

The References disclosure is assembled after streaming completes and starts
collapsed. Visible reference links are deduplicated by root for navigation, while
their hidden queries retain the exact cited child UUIDs so unrelated siblings remain
redacted. Opening all references uses an OR query over the exact cited UUIDs without
changing the visible search field.

## Session, Cancellation, and Debugging

Conversation, activities, scope, evidence, and traces are server-memory session
state. Only user and completed assistant prose become later canonical conversation
context. Clear Chat and Stop abort active provider work; logout, auth reset, lock,
or process restart releases run state.

Developer-eye mode shows route validation, selected action/reason, root-prefix
retention, evidence payload size, retries, final writing, approximate token counts,
and per-step duration. Agent Debug always retains the latest run in session memory
so it can be opened after a failure. Its evidence event contains the exact one
payload sent for answer generation, and Copy all produces complete formatted JSON.
Traces are never persisted.

## Web action loop

Each run freezes `pref.ai.web_access_mode` with the note scope. `none` exposes no
web action schema, while `contextual` and `full` expose only `open_web_pages`.
Full mode permits direct public page URLs proposed by the model; it does not add a
search-engine action. Ordinary lookups open a Google results URL through
`open_web_pages`, then may open useful result URLs in another batch. Google and
source pages use the application-owned fetcher, independent of the inference
provider. The application validates every contextual URL
against capabilities built only from user messages, disclosure-safe selected or
investigation evidence, and retained web evidence. It never scans hidden NoteStore
records to authorize a URL.

The conditionally loaded `web_browsing_v1` skill describes batching, citations,
partial failures, and the untrusted-content boundary. Application checks remain
authoritative. Page-open actions accept at most eight independent URLs. Page work
is concurrent and results stay in submitted order; normalized duplicates share one
retained evidence object.

Opened pages enter a bounded, session-owned evidence store. Subsequent planning
can reuse them without another request, but links merely mentioned by their page
bodies do not become contextual capabilities. The final response receives exact
`[[web:UUID]]` tokens and a catalog of allowed external references. Streaming,
reload, copying an answer to a note, and mixed note/web reference rendering all
use that same authorization scope.

HTML extraction also records a bounded, deduplicated set of visible labeled links.
Each receives a separate `page_link` reference whose URL and label came from the
opened source page; this does not fetch the target or authorize it in contextual
mode. The opened document remains an `opened_page` reference. Direct article or
report summaries cite that opened document. Aggregator, index, directory, and
search-result summaries use the relevant item `page_link` references, so the
rendered References entries open the actual listed destinations. The browsing
skill and final prompt require body-only cited bullets for those list summaries and
forbid claims about an unopened target beyond its visible label and source-page
metadata.

## Provider Details

OpenAI calls set `store: false`. Encrypted namespaces store the API key encrypted
with the namespace DEK; plaintext namespaces hold it only in authenticated server
session memory. The raw key is never returned to the browser or included in traces.

Completed OpenAI calls contribute API-reported uncached input, cached input,
cache-write input, and output usage to a process-memory cost tracker. The tracker
uses model-specific and long-context pricing, is labeled estimated because an
interrupted request may not return final usage, and is cleared only by Reset or
process restart.

## Main Files

- `app/services/agent/runtime.py`: orchestration and streaming.
- `app/services/agent/scope.py`: immutable user-bounded scope.
- `app/services/agent/investigation.py`: ordered complete-root retention.
- `app/services/agent/evidence_serialization.py`: full nested evidence JSON.
- `app/services/agent/context.py`: route and direct final request assembly.
- `app/services/agent/retrieval_settings.py`: provider evidence-token limit.
- `app/services/agent/cloud_privacy.py`: cloud disclosure policy.
- `app/services/agent/trace.py`: session-only debug events.


## Tag Proposal Operations

An explicit chat request can select `tag_proposals`. A second structured interpretation resolves generation, bulk acceptance, or bulk removal and its scope/filter; ambiguous or unsupported requests receive clarification without mutation. Unrelated conversation remains read-only.

Generation captures the search-visible trees. Visible ancestors supply content, but unseen sibling branches do not enter tagging evidence. Parent proposals inherit normally to unseen descendants. Privacy exclusions remain enforced before disclosure.

- Existing vocabulary is accepted tags in the entire disclosed search context, computed before batching and shared by all requests; never the namespace catalog or pending proposals. `pref.ai.tagging.vocabulary` is one categorical permission (`existing`/`new`), while `pref.ai.tagging.focus` remembers the exact last selector choice (`existing`/`new`/`both`). Submitting existing-only saves existing permission; new-only or both permits new tags. There is no separate vocabulary setup question.
- `pref.ai.prompt.tagging` contains editable tagging instructions, available through **Tagging prompt and vocabulary…** in the menu.
- Every batch receives the exact generation request. A named subject is a binding semantic filter rather than a general hint: examples disambiguate its intended meaning, proposals favor specific concepts/methods/entities inside that subject, and unrelated notes or broad neighboring classifications are omitted.
- Existing-only requests explicitly require exact supplied vocabulary terms, without synonyms or variants. Every batch payload also carries an explicit machine-readable pass mode. New-only instructions require a final case-insensitive comparison against the supplied accepted vocabulary before output.
- Each batch tolerates up to 10% invalid tag assignments, dropping those assignments and omitting notes left without valid tags. A separate 10% threshold applies to duplicate or non-batch note-ID entries; tolerated entries are discarded whole. Validation distinguishes an ID in another batch of the current permitted scope, a real namespace note outside the current permitted scope, and a nonexistent ID. It uses frozen ID-set membership only and never reads an out-of-scope note. A real out-of-scope ID may have been disclosed under an earlier conversation scope, so it is not labeled proof of a new disclosure leak. The denominators are distinct case-insensitive note/tag assignments and total proposal entries respectively. Existing-only accepts terms found either in disclosed context vocabulary or, after inference, in accepted namespace tags; the latter are canonicalized without disclosing the namespace catalog to the model. New-only rejects accepted tags disclosed in the context. If a new-only candidate happens to match an accepted tag elsewhere in the namespace that was never disclosed to the model, validation silently drops it without counting it as a model error. Both mode permits existing or new terms. Invalid syntax and command tags are invalid in every mode. Above either threshold, the model receives the cumulative validation failures and may regenerate the complete batch up to three times; if the third correction still fails, the pass fails atomically. Malformed response structure remains strict.
- Generation intent never selects the per-pass focus. Every generation request asks the three-way structured focus question, preselects the exact previous choice, and keeps all choices available. The answer updates both the remembered focus and the two-way vocabulary permission in one submission. Request wording and model interpretation cannot skip the question, including explicit requests for existing, new, or both. Existing focus validates output against batch vocabulary.
- The configured evidence budget determines batching. Evidence above 1× requires explicit confirmation, combined with the focus question when one is needed. Randomize visible root-tree order before batching so display-adjacent roots do not systematically share requests. Complete visible root trees remain together and preserve their internal hierarchy/order; every requested tree is reviewed. Processing time is hidden and paused during questions; no predicted duration. Proposal dialogs reuse the shared modal-content and form-actions styles.
- New-only focus strictly excludes disclosed accepted vocabulary terms (case insensitive). The namespace catalog remains undisclosed, so post-inference validation silently drops a collision with an accepted namespace tag the model could not know about.
- Every pass uses token-sized requests, configured alongside the evidence limit in AI settings: `pref.ai.openai.tagging.batch_tokens` (default 100,000). Bounds match the corresponding evidence setting (500–500,000). Shared vocabulary overhead counts toward every batch. Whole roots may exceed the target window, but the full request must still fit the model context. There is no fixed note-count subdivision or partial-JSON parsing. The inline progress bar advances by completed input-token weight after each validated batch.
- Chat tag generation renders its choice and progress controls inside the transcript. The focus selector has three real options and no explanation paragraph or placeholder; Continue explicitly submits the selected option. No preparation overlay. Chat input and surrounding UI are locked while operation controls stay usable. Non-chat regions are inert, greyed, slightly blurred, and use a not-allowed cursor. Transcript rerenders preserve the live operation element and its selected value/focus. Programmatic acceptance/removal stays in the ordinary chat working state through its atomic update and never creates a progress or cancellation panel. Menu choice and confirmation dialogs use normal modals, but submitting a programmatic acceptance/removal operation shows only the application busy state with no second progress modal.
- An application-owned modal locks normal interaction while the batch guard rejects conflicting server mutations. Pending question answers remain available, and Cancel aborts the stream before final application. The final synchronous commit phase disables Cancel.
- Validated proposals accumulate only in session memory. New terms from completed batches are supplied separately to later batches as optional `prior_batch_new_tags`, allowing consistent reuse without treating them as accepted or required vocabulary. All batches must succeed before one database transaction writes the result. Canonical note sources and inheritance/search indexes are then published without an async yield, and existing undo/redo is cleared only when changes were applied. No bulk undo entry is created. After a successful mutation, the client discards the active view's root window and pagination terminal state before fetching a fresh first window, so proposal-driven search-membership changes cannot strand infinite scroll.
- A successful generation response lists each newly added proposal and cites every note that received it. Inline numbered markers remain clickable, while the ordinary expandable References section is replaced for this response type by one **Show all new tag proposals** link. That link uses the same combined exact-note query as Open all references. Canonical conversation history retains the tag names while stripping citation UUIDs before later model calls; subsequent tagging also reads each note's authoritative pending proposals and explicitly excludes duplicates.
- Failure/cancellation applies no pending results; no-change results preserve history. Individual proposal controls retain their undo semantics.

Bulk acceptance/removal resolves the complete requested target set programmatically, independent of provider disclosure and token limits. Current context is the default; entire-namespace scope must be explicit. Menu and chat support an exact case-insensitive tag filter or all proposals. These operations execute directly without an additional confirmation or tagging inference. Removing proposals creates no rejection memory.

Implementation: `app/services/agent/tagging.py`, `tagging_run.py`, `app/services/bulk_operation.py`, and `app/usecases/bulk_tag_proposals.py`. Structured questions and direct menu operations use authenticated `/api2/ai/proposals/*` endpoints.


## Session history and explicit regression replay

`history.py` binds an inference recorder to the scoped run using task-local context.
The OpenAI adapter records logical call inputs, actual HTTP bodies, structured
attempt outputs, and raw text-stream chunks, including errors and cancellation.
`AgentTraceStore` retains every run for the session while its debug snapshot still
returns the latest run. Authenticated `GET /api2/ai/history` exports chronological
input/output pairs with `Cache-Control: no-store`. Clear Chat/logout/reset remove
history; there is no new persistence or provider-side storage.

History recording never inserts old instructions or evidence into new requests.
Each call records precisely its own context. Skills in future replay steps must
be explicitly included; loading a skill once does not make it permanent history.
The existing scoped investigation path records skill activation for its policy;
that activation record alone does not prove the skill text was sent to a model.
The exported actual request is authoritative.

`evals/` uses the production inference adapter and response models for explicit
prompt tests. Ten independent repetitions report rates, with structured action
expectations or an Instructor-validated output judge. This initial replay layer
checks decisions/outputs; it does not execute UI or note mutations. See
[the suite guide](../../evals/README.md) for prompt bindings, fixture authoring,
comparison rules, and limitations. Additional application actions remain planned.

## Product help route and browser acknowledgments

`ScopedRouteEnvelope` requires `help_topics`: a nonempty, unique supported list for
`metalist_help`, and an empty list for all other routes. This is structural
validation; there is no keyword-based intent override. The content-free routing
request includes ten topic descriptions. `build_help_messages` adds only those
selected skills to a fresh canonical conversation and the compact menu catalog.
The second Instructor call returns `MetaListHelpResponse(answer, menu_id)`. Help
prose is buffered until the structured response validates. Overrides are loaded
through the existing skill registry, recorded with their effective text, and
never saved as subsequent conversation instructions.

The shared JSON menu catalog is the application-owned destination allowlist.
`dialog` invokes an existing form-opening handler; `palette` opens and highlights
an existing entry without invoking its operation. Help cannot change preferences
or submit a form. Explicit proposal mutations still use the separate tagging
route. The browser checks scope/cancellation/modal availability and visible DOM,
then POSTs `{request_id, status, detail}` to `/ai/menu-result`. Requests are bound
to the authenticated session, single use, and expire after 30 seconds. Unknown,
wrong-session and replayed acknowledgments return 409; malformed input returns
422. Cancellation closes pending futures. The application appends actual opening
status to the answer; model wording is not an execution record.

`AgentTraceStore.export_history` associates `MENU_REQUESTED` and `MENU_RESULT`
with the producing output pair under `application_events`, retaining request IDs,
menu IDs, scope and outcome. History remains session-only. Tests use disposable
state/controlled handlers; opt-in live cases only evaluate model choices/answers.
