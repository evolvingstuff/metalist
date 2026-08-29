# Agent Harness: Read-only Foundation

## Current Scope

- MetaList owns the orchestration loop; the HTTP route does not call Ollama directly.
- Instructor owns every JSON/Pydantic action-selection call over Ollama. Natural-language final synthesis streams through the direct Ollama adapter.
- LiteLLM, remote providers, and note mutations are deferred. MetaList now has an
  application-owned runtime skill registry; the Search skill is the first skill.
- One user-selected model handles action selection and final synthesis through an explicit model-policy seam.
- One MetaList-owned Ollama daemon is shared across namespace processes. It starts
  on demand on the dedicated loopback port `11435` with a 32,768-token default
  context, cloud features disabled, and strict persisted PID/listener ownership.
- Internal actions are a closed Pydantic discriminated union: `search_notes`,
  `read_notes_by_id`, `respond`.
- Ollama receives a flat, fully required Pydantic envelope instead of a root `oneOf` schema. `kind` alone selects the action; inactive required fields are placeholders and are ignored when the envelope is projected into the strict internal union. The prompt still requests empty placeholder values to keep traces clear.
- Search/read tools use the hydrated in-memory `SearchIndex` and `NoteStore`; agent reads never query SQLite.
- The existing `/api2/ai/chat` NDJSON contract remains the user-facing streaming boundary.

## Runtime Flow

```text
POST /api2/ai/chat
  → AiChatSessionStore.start_turn
  → ManagedOllamaRuntime.ensure_running (shared loopback daemon)
  → AgentRuntime
      → preload selected model + verify active context allocation
      → ContextBuilder(system prompt + canonical conversation)
      → Instructor + Ollama typed route call (non-streaming)
      → Pydantic validation; Instructor performs one schema-guided retry if invalid
      → if search_notes: activate Search skill in transient context
      → Instructor + Ollama typed search-query call (non-streaming)
      → PermissionPolicy
      → search_notes/read_notes_by_id tool
      → append transient action + tool result
      → repeat or select respond
      → Ollama final synthesis (streaming)
  → AiChatSessionStore.complete_turn
```

The model receives flat route and search-query envelopes through Instructor
`JSON_SCHEMA` mode on Ollama's OpenAI-compatible endpoint. Instructor places each
Pydantic schema in `response_format`, so Ollama constrains generation before
Instructor performs Pydantic validation. MetaList does not duplicate serialized
schemas in prompt text. The first call chooses only the high-level action. If it
chooses `search_notes`, MetaList injects the Search skill into a second call that
produces the concrete query. This keeps MetaList search syntax and examples out of
the base routing prompt. The skill message exists only for that parameterization
call; the following route call sees the search result but not the skill message.

Tool mode remains excluded because some nominally tool-capable local models return
JSON content instead of a tool call, which breaks tool-mode parsing/reasking. The
flat wire shapes avoid root-union/reference compatibility failures without
weakening the internal action types. Only fields active for the selected route are
semantically validated. `respond` appears first in the route enum, and ordered
schema examples are omitted to avoid position bias in small local models. The
Search skill requires a positive tag or quoted-text term in every `OR` clause;
Instructor retries exclusion-only searches. This restriction applies only to
agent-generated searches. The final user message is authoritative for query
generation: prior topics enter a query only when the current request explicitly
depends on them, and a topic change never justifies negating the old topic.
A broad topical request searches both the tag and note-text forms in its first
query—for example, `foo OR "foo"` or `foo bar OR "foo bar"`—unless the user
explicitly requests tag-only or text-only scope. A later revised search remains
available when the model identifies missing evidence or concrete false positives.
The route and query schemas explicitly tell the model that search results carry
their bounded content in `notes[].content_text`, so returned note IDs are not
handles that require another read. Before query generation, the runtime also
compares normalized repeat-search rationale text against completed query text; an
exact matching selection skips the redundant Search-skill
call. Before tool execution, it compares normalized generated-query semantics and
page number against completed searches as a second guard. Either exact repeat is
skipped and synthesis continues from the already-retrieved evidence. Structured calls use temperature `0` and allow one
Instructor retry. Final synthesis retains the selected thinking level and streams
thinking/content through the existing UI.

The packaged base system prompt prefers Markdown final answers and allows LaTeX math and fenced Mermaid diagrams when useful. A saved namespace system-prompt override intentionally replaces the packaged prompt rather than being merged into it.

The managed runtime lives outside namespace state. Atomic startup locking and a
strict state record let concurrent namespace processes reuse one detached daemon
without racing. MetaList refuses an unowned listener on its dedicated port and
verifies that the recorded PID is the sole listener before reuse. It launches
`ollama serve` with `OLLAMA_CONTEXT_LENGTH=32768`,
`OLLAMA_HOST=127.0.0.1:11435`, `OLLAMA_NO_CLOUD=1`, and
`OLLAMA_NUM_PARALLEL=1`; request-body logging and CLI history are explicitly
disabled. Before the action loop, the inference adapter preloads
the selected model and compares its declared maximum and `/api/ps` active context
against the required window. The `MODEL_CONTEXT` trace event preserves those
exact values for post-failure inspection.

Harness rule: if a model call must return JSON/Pydantic data, it goes through Instructor. If a model call returns natural-language streaming output, it goes through the provider adapter directly. LiteLLM can be introduced behind the same inference seam when multiple providers, routing, fallbacks, or cost accounting are actually required.

## State Boundaries

### Canonical conversation

- User messages and completed assistant-visible answers only.
- Failed turns are excluded from later model context.
- Provider reasoning, actions, searches, note payloads, and validation retries never enter later turns.

### Working context

- System prompt, structured actions, tool results, activated skill messages, and
  final-response instruction for one run.
- The three packaged Markdown prompts and every registered skill can be replaced
  by namespace-scoped client-preference overrides from `Agent prompts…`. The
  runtime resolves immutable prompt and skill sets at run start, so edits affect
  the next run and cannot change an in-flight run.
- Built append-only during the active run and discarded when it ends.
- Skill content is appended only after its trigger action and recorded as a `SKILL`
  trace event. It is never inserted into old prompt tokens or copied into canonical
  history.

### Debug trace

- The latest trace is always captured in session memory so a completed or failed run can be inspected after the fact.
- Only the current or most recently completed run exists; starting a new run replaces the previous trace.
- Instructor hook states are appended live while a call is running: attempt start, Ollama response received, validation, retry/final failure, and success. Exact transformed model requests, every retry response/error, schemas, provider reasoning, usage, policy decisions, tool arguments/results, timing, final response, and errors are captured.
- Every call to Ollama appends its own `OLLAMA_REQUEST` entry before the response: each Instructor action-selection attempt (including retries and later post-tool selections) and the direct final-response stream. The entry contains the HTTP method, endpoint, and complete JSON body with the ordered messages used at that moment, including canonical user messages and transient tool/final-response instructions. Structured bodies are captured from the HTTP transport after Instructor adds the native `json_schema` response format; the OpenAI-compatible transport does not perform hidden retries.
- The debugger does not substitute a standalone system-prompt entry for a request. The system prompt appears in its real position inside each outbound request's `body.messages` array alongside the corresponding user message.
- Logout, runtime lock, auth reset, or process restart clears the trace and resets exact-detail visibility to its on-by-default state. Clear Chat removes the trace while preserving the current visibility toggle.
- No trace rows or payloads are persisted to SQLite, files, browser storage, or canonical conversation history.

## Read-only Tools

### `search_notes`

- Uses normal MetaList search syntax: tags are unquoted, text is quoted, `-` excludes, uppercase `OR` separates clauses.
- Query generation is a separate Instructor call made with the transient Search
  skill active. Invalid syntax fails Pydantic validation and receives the single
  structured-output retry.
- Reports both the total number of matching note nodes and the number of top-level
  result trees, matching the search UI's counting semantics. A matching parent and
  child therefore count as one result tree even though both matching nodes appear
  together when that root is selected for a bounded result page.
- Returns one one-based page of top-level result trees plus their matching note
  nodes. The default page size is 50 result trees and the namespace owner can
  configure 1–100 in `AI Agent Settings…`.
  `has_next_page`/`next_page` let the agent request another page only when the
  available page is insufficient.
- Each payload begins with an explicit content contract: the returned notes are
  content-bearing rather than ID-only previews, `notes[].content_text` is the
  bounded text to synthesize immediately, and no follow-up read is required.
  The final-response instruction repeats this contract and forbids substituting
  generic background knowledge when current-run note content exists.
- Orders pages by MetaList's canonical user-ranked roots and then visible tree order
  within each root. The unordered SearchIndex membership set never determines
  result position.
- Notes near the top of a page are generally more recent or more highly ranked by
  the user. The Search skill identifies that order as a prioritization hint, never
  as proof that a result is relevant.
- Returns at most the configured characters for each note (default 2,000,
  configurable from 500–10,000), with the original disclosed length and an
  explicit truncation flag. A second configurable limit caps total note text per
  result page (default 20,000; range 5,000–100,000) and distributes that budget
  across returned matching nodes without dropping their metadata. Every note also includes its explicit user-assigned
  tags, parent/root IDs, and ISO created/updated timestamps.
- Only IDs returned by the search index are serialized. Non-matching children that
  the main UI represents as gray search-redaction bars are omitted completely;
  neither their text nor an ancestor preview is included in the tool payload.
- `@password` note values are independently replaced with a redaction marker
  before either the model context or Agent Debug tool payload is built.

### `read_notes_by_id`

- Accepts 1–12 unique note UUIDs.
- Directly returns bounded plain text and metadata from the in-memory store without
  a search. It is for UUIDs already known in transient context and is not a normal
  follow-up to `search_notes` or a way to bypass per-note limits.
- Applies the same configured per-note and total-page character limits plus
  `@password` redaction, and reports missing IDs explicitly.

No create, edit, move, trash, delete, SQL, filesystem, or shell action exists in the action schema or tool registry.

## UI

- Live `action_status` events append compact activity panels to the assistant turn; no progress or error status surface exists under the composer. Panels distinguish model waits/validation, Instructor retries, skill activation, note tools, cancellation, and final-response writing with different tinted backgrounds. Every selected-action panel includes the model's compact required reason/basis; a later search is labeled `Search again` with its rationale. Model waits name the operation (`choosing next action` or `preparing MetaList search query`) and attempt. Every diagnostic panel separately shows an approximate input-token count, estimated from the actual serialized wire body when one exists and from the current working context otherwise, using a provider-neutral four-characters-per-token heuristic. Search execution panels show the exact MetaList query and requested page in eye-mode, then report returned/total result-tree counts, matching nodes on the page, and current/total pages. A programmatically skipped duplicate search is explicit and keeps its query in the same contrasting monospace treatment. The compact hidden-eye `Working` indicator keeps queries concealed. Each logical operation updates one panel as it progresses: `Preparing action selection` merges into the resulting Ollama attempt, one Ollama attempt replaces wait/response/validation text in place, and tool and response panels replace their active label with the completed label. Retry/failure events remain distinct historical panels. Token metadata and panel state remain in the session transcript but never enter canonical model history.
- During an active turn, Send becomes an enabled red Stop control. Cancelling aborts the browser request, cancels the server stream, records `Cancelled by user` in the turn, and immediately unlocks the composer controls. Clear Chat remains available during a run; it invokes the same cancellation path, waits for the active browser request to settle, and only then clears the chat session and latest trace.
- Each structured call reports its current attempt and maximum attempt count. Validation/provider failures identify the failure type and whether Instructor will retry; the exact error remains available in the debug trace.
- Exhausted structured retries produce a short user-facing error panel that directs the user to Agent Debug; Instructor's full exception and attempt payloads are not dumped into the chat.
- The `Thinking` disclosure renders only when the selected model actually emits reasoning content. Thinking Off therefore never shows a misleading `Thinking` heading.
- Assistant note citations are current-run evidence only. The runtime attaches the exact non-redacted note IDs returned by tools during that run to every final-content event; the server rejects a changing scope, strips known note citations outside that allowlist before storing the answer, and excludes bracketed citation metadata from later canonical model history. This prevents unrelated references from an earlier answer from leaking into a new answer even if the model repeats them. Within the current-run scope, citations accept the prompted `[[UUID]]` syntax, bare existing note UUIDs, and known UUIDs wrapped as inline code. Common model-produced Unicode dash separators are normalized programmatically before lookup. The chat renderer replaces each recognized inline occurrence with the specifically cited node's quoted, non-clickable first content line, then groups the automatic clickable References section by top-level root. Multiple child citations under one root produce one root link; `Open all references` appears only for multiple distinct roots and executes their exact `UUID OR UUID` query in a temporary reference-source tab. Individual and combined reference navigation keep the internal query out of the search field and expose the existing dismissible Reference source indicator to restore the prior context. Fenced code, links, and unknown UUIDs remain literal.
- The chat header has a default-off eye toggle that hides or reveals all developer diagnostic activity panels without deleting their state. Its namespace-scoped preference survives refresh and restart. While those panels are hidden, an active response still shows one compact `Working` indicator with the latest phase and elapsed time; it disappears when answer content begins. The trace launcher is never styled as selected merely because a trace exists. Its large debugger modal closes from `×`, Escape, or a backdrop click.
- `Show exact prompts, model responses, and tool payloads` is checked by default. It controls detail visibility and can be changed before, during, or after a run. It never controls whether the latest trace is retained.
- The debugger renders the latest run as a chronological expandable outline. Enabling exact details exposes each row's full JSON payload.

## Main Files

- Runtime: `app/services/agent/runtime.py`
- Diagnostic token estimation: `app/services/agent/token_estimation.py`
- Actions: `app/services/agent/actions.py`
- Prompt resources: `app/services/agent/prompts/*.md`
- Prompt loading/override validation/context assembly: `app/services/agent/prompts/__init__.py`, `app/services/agent/prompt_settings.py`, `app/services/agent/context.py`
- Skill resources/registry: `app/services/agent/skills/*.md`, `app/services/agent/skill_settings.py`
- Model policy: `app/services/agent/model_policy.py`
- Permissions/tools: `app/services/agent/permissions.py`, `app/services/agent/tools.py`
- Transient trace: `app/services/agent/trace.py`
- Ollama runtime/seam: `app/services/managed_ollama_runtime.py`, `app/services/agent/ollama_inference.py`, `app/services/ollama_provider.py`
- API: `app/api/routes/ai.py`
- Debug UI: `app/static/js/modules/ai-chat/ai-agent-debug-view.js`
- Prompt editor UI: `app/static/js/modules/modals/agent-prompt-editor-modal.js`
- Tests: `tests/unit/test_agent_prompt_settings.py`, `tests/unit/test_agent_runtime.py`, `tests/unit/test_ai_chat.py`, `tests/unit/test_ai_routes.py`, `tests/unit/agent_prompt_service.test.mjs`

## Deferred Seams

- LiteLLM can replace or wrap `OllamaInferenceAdapter` without changing the runtime/tools.
- LiteLLM can wrap Instructor at the inference seam when multiple providers, routing, fallbacks, or cost accounting justify the additional layer.
- Model routing can extend `SingleModelPolicy` at explicit inference-purpose boundaries.
- Additional skills can extend the registry with their own trigger action, packaged
  Markdown resource, namespace override key, and trace event.
- Mutations require new action types, tool specs, permission decisions, confirmation UX, and regression tests; they must not be added by widening the current read-only handlers.
