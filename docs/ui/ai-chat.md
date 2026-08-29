# AI Chat and Read-only Agent Harness

## Scope
- MetaList chats with an Ollama model through an authenticated, application-owned agent runtime.
- The runtime can search and read hydrated notes but cannot create, edit, move, trash, or delete anything.
- Note searches and reads use the existing in-memory `SearchIndex` and `NoteStore`; agent reads never query SQLite.
- MetaList owns one shared local Ollama daemon for every namespace. It starts the
  daemon on demand on `127.0.0.1:11435`, keeps it separate from any user-managed
  Ollama listener, and refuses to attach when the ownership record and listener
  PID do not match.
- Instructor owns JSON/Pydantic calls. The first call chooses a high-level action;
  `search_notes` then activates the packaged Search skill for a second structured
  query-generation call. Final prose still streams directly from Ollama. LiteLLM
  and remote providers remain deferred behind explicit seams.

## Configuration
- Open `AI Agent Settings…` from the command palette or use the gear button in the chat header to inspect the managed runtime, view downloaded models, save a selected model, and set bounded note-retrieval limits. The chat composer also provides immediate model and thinking-level selection beside Send.
- Ollama is currently the only provider; the provider field is present so future providers can share the same configuration surface.
- Model listing, model download, and chat start the shared daemon lazily. MetaList
  launches the installed `ollama serve` executable with
  `OLLAMA_CONTEXT_LENGTH=32768`, `OLLAMA_HOST=127.0.0.1:11435`,
  `OLLAMA_NO_CLOUD=1`, `OLLAMA_DEBUG_LOG_REQUESTS=false`, `OLLAMA_NOHISTORY=1`,
  and `OLLAMA_NUM_PARALLEL=1`. The daemon uses Ollama's normal
  shared model store, so models downloaded by an existing local installation remain
  available.
- Runtime ownership is coordinated across namespace processes through
  `~/MetaList/runtime/ollama/ollama-runtime.json` plus an exclusive startup lock.
  The detached daemon is reused across namespace and MetaList restarts rather than
  being stopped when one namespace closes. Its bounded direct-append log is
  `~/MetaList/logs/ollama-managed.log`.
- Opening the chat panel asks the managed daemon for its installed models so the composer selector is current.
- AI Agent Settings loads models already downloaded in the managed Ollama instance. Save persists the explicitly selected downloaded model. Download is a separate action: the user chooses the exact name from the linked official Ollama library and explicitly starts the pull. MetaList does not scrape the library or depend on an undocumented catalog API. Status and byte progress stream from Ollama's supported `/api/pull` endpoint; success refreshes the downloaded-model list without selecting or saving the new model.
- Selected model, thinking level, maximum characters per returned note (default 2,000; range 500–10,000), result trees per search page (default 50; range 1–100), and total returned note characters per page (default 20,000; range 5,000–100,000) are namespace-scoped client preferences. In a password-protected namespace they use the existing encrypted client-state persistence path. The managed runtime URL and context are application invariants, not client preferences.
- Open `Agent prompts…` from the command palette to inspect and override the
  packaged agent system prompt, final-response control template, tool-result
  wrapper, and registered skills. Skills render as collapsed sections with an
  explicit disclosure arrow and trigger-action label so the editor scales beyond
  the first Search skill. Overrides are
  namespace-scoped client preferences, use the same encrypted persistence path in
  protected namespaces, and apply to the next agent run. `Restore packaged
  defaults` removes all prompt and skill overrides. Template placeholders remain
  strictly validated.
- The compact selectors immediately left of Send choose the model and show `Thinking Off`, `Low Thinking`, `Medium Thinking`, or `High Thinking`, with Low as the default. Changes persist immediately. MetaList sends native Ollama `think: false` for Thinking Off and the corresponding level string otherwise. Model support varies; GPT-OSS supports Low/Medium/High but cannot disable thinking, so Thinking Off is unavailable for GPT-OSS selections.

## Panel Behavior
- `Show/Hide AI Chat` is available from the command palette and from the notes-view right-click menu outside edit mode.
- AI chat and the right-side activity calendar are mutually exclusive. Enabling either view atomically disables the other preference.
- The panel occupies the right third of the viewport by default. The notes shell narrows into the remaining space instead of being covered.
- Drag the panel's left separator to resize it. Chat remains at least 280 px wide and leaves at least 480 px for the notes area. The focused separator also supports Left/Right Arrow plus Home/End. The chosen width is saved as a client preference, restored after refresh, and temporarily clamped when the viewport is too narrow without replacing the saved preference.
- The header provides a default-off eye toggle for developer diagnostic activity panels, plus debug trace, clear, settings, and close actions. Its namespace-scoped state persists across refresh and restart; hiding panels does not delete their state or change the debug trace. A hidden-diagnostics run still displays one compact live `Working` indicator with the latest phase and elapsed time until answer content starts. `Enter` sends; `Shift+Enter` inserts a newline. Debug trace opens a large modal rather than squeezing execution details into the chat panel; the launcher does not stay selected when a trace exists, and the modal closes from `×`, Escape, or a backdrop click.
- Dragging the message field's lower-right resize handle saves its height as a client preference and restores it after refresh.
- While the current response is streaming, the composer remains editable so the next message can be drafted. Send becomes an enabled red Stop button that aborts the active browser/server stream; cancellation is recorded as `Cancelled by user` inside the turn. Model and thinking-level selection remain disabled until the response finishes or is cancelled. Clear Chat remains enabled: it cancels and awaits the active request before clearing the transcript and latest trace.
- Right-click a completed assistant response and choose `Copy Response` to copy it as a MetaList note payload. The raw response Markdown is preserved and automatically tagged `@markdown @llm`; the system clipboard receives rendered rich HTML plus the raw Markdown as plain text. The copied response can be pasted as a sibling or child note, but reference-paste actions remain unavailable until it exists as a real MetaList note with its own UUID.

## Streaming and Session State
- `/api2/ai/chat` streams typed NDJSON events: `action_status`, `thinking_delta`, `content_delta`, `done`, or `error`. The endpoint explicitly bypasses response compression and proxy buffering so small answer tokens reach the browser immediately rather than collecting until completion.
- A chat turn first exposes one collapsing managed-runtime activity while the daemon
  is started or reused. Before inference, MetaList preloads the selected model,
  reads `/api/show` and `/api/ps`, records the model maximum/loaded/required context
  in Agent Debug, and refuses to continue unless the active allocation satisfies
  the required context. For Qwen 2.5 7B this verifies an active 32,768-token window.
- High-level route selection is a non-streaming Instructor + Ollama `JSON_SCHEMA`
  call. Instructor sends the flat required Pydantic schema through Ollama's native
  OpenAI-compatible `response_format`, validates the result, and performs one
  schema-guided retry for semantic validation failures. `kind` selects the action;
  inactive note-ID placeholders are ignored. `respond` appears first and ordered
  action examples are omitted to avoid small-model position bias. After a
  `search_notes` route, MetaList activates the Search skill and makes a second
  Instructor call whose smaller schema contains the query, one-based page, and reason. Search
  syntax, positive-clause rules, and abstract `foo`/`bar`/`baz`/`"lorem ipsum"`
  examples live in that editable skill rather than the routing prompt. The skill
  also explains that results near the top are generally newer or more highly
  user-ranked, while explicitly treating order as a hint rather than relevance
  proof. For a broad topical request it combines tag and exact note-text coverage
  in the first query (`foo OR "foo"` or `foo bar OR "foo bar"`) unless the user
  explicitly requests tag-only or text-only scope. It treats the final user message as the current request and forbids
  carrying unrelated earlier topics into a new query as negative terms. A
  complete relevant search with `has_next_page: false` must proceed to an answer;
  a second query is allowed only for specifically identified missing evidence or a
  concrete false-positive pattern, never merely to reduce the match count. The
  runtime still permits genuinely revised searches and later pages, but skips an
  already-completed semantically equivalent query/page before tool execution. Tool
  mode remains excluded because nominally tool-capable local models may emit JSON
  content without a tool call. Final synthesis remains direct natural-language
  Ollama streaming.
- Visible status events append compact tinted activity panels to the assistant
  turn; status and errors are never written beneath the composer. Model request/validation panels are violet, retry/failure panels are amber,
  skill activation is cyan, note tools are blue, and response writing is green. A
  live search panel includes the exact executed query in a contrasting monospace
  token; on success the row reports returned/total result-tree counts, matching
  note nodes on that page, page position, and exact query separately.
  A requested page that does not exist is reported explicitly. Every
  selected-action row includes its required compact reason/basis; subsequent
  searches say `Search again` and expose why. A skipped exact-repeat search is
  also explicit, with its query kept in the monospace token. Each logical
  operation updates one panel from its active label to its completed label: for
  example, `Writing response` becomes `Response complete`, and the wait, response,
  and validation phases of one Ollama attempt share one panel. The preceding
  `Preparing action selection` phase is replaced by that same model-operation
  panel as soon as its wire request starts. Every visible diagnostic panel carries
  a separate approximate input-token count; actual wire-request bodies are
  estimated directly, while non-model phases show the current working-context
  estimate. Counts use a provider-neutral four-serialized-characters-per-token
  heuristic and remain attached to rehydrated session activity. Retry and failure
  events remain separate so the reason for another attempt stays visible. The sequence survives session
  rehydration but is excluded from later model context. With diagnostic panels
  hidden, the compact `Working` indicator reports progress without exposing the
  query.
- Instructor hooks report the specific operation being performed, approximate input-token count, `attempt N of M`, Ollama response receipt, schema validation, failure type, and retry/no-retry state as they happen. The same sequence is appended to the always-retained debug outline as `MODEL_STATUS` events; exact prompts/responses remain in the detailed attempt entries.
- Thinking and answer content render separately. A `Thinking` disclosure exists only after the model emits real reasoning content, so Thinking Off never shows a misleading heading. Thinking and answer events each include a cumulative server-rendered snapshot, so Markdown and completed LaTeX expressions format while text is still streaming. An open reasoning disclosure collapses when the first answer chunk arrives. The user can reopen it afterward, and that explicit choice is preserved while later answer chunks render. Mermaid source is finalized into a diagram when the turn completes.
- If structured retries are exhausted, chat shows a compact tinted failure panel and directs the user to Agent Debug instead of rendering Instructor's internal exception dump.
- Assistant thinking and answers use MetaList's Markdown renderer while streaming, including completed LaTeX delimiters rendered as MathML. Fenced `mermaid` diagrams are rendered by the strict local Mermaid runtime after completion.
- Existing note UUIDs cited in an assistant answer render inline as quoted, non-clickable previews of the specifically cited note's first content line, never its UUID. References are limited to non-redacted notes actually returned by tools during the current run; citations outside that scope—including invented UUID-shaped values—are removed before display/storage, and bracketed citation metadata is removed from later Ollama conversation history. The completed stream performs one final sanitized render so a transient raw citation cannot remain visible after the answer finishes. A new note-free request therefore cannot inherit references from a prior note-backed answer. The renderer groups cited nodes by top-level root and appends one compact clickable MetaList reference per unique result tree. Multiple cited children under one root therefore produce one root reference. When there is more than one root, `Open all references` opens the exact root `UUID OR UUID` result set. Both individual and combined links use the established temporary Reference source context: the internal query stays hidden from the visually empty search field, and its dismissible X returns to the prior context. The prompted `[[UUID]]` form, bare UUIDs, and known UUIDs wrapped as inline code are recognized; common Unicode dash substitutions are normalized programmatically. UUIDs inside fenced code and UUID text inside an existing link remain literal.
- Agent search counts use top-level result trees, matching the main search UI,
  and paging uses those same result trees. Each page contains at most the user's
  configured number of result trees plus all matching nodes under those selected
  roots. The agent may request `next_page` when the
  current page is relevant but insufficient; a new or refined query always starts
  at page 1.
- Agent result pages follow MetaList's canonical user-ranked root order and visible
  tree order within each root. SearchIndex membership is never treated as an
  ordering source. Broad summaries should continue through relevant pages; if they
  stop early, the answer must identify the retrieved page scope and must not imply
  that a subset represents every match.
- Each returned node includes bounded plain text, explicit user-assigned tags,
  parent/root IDs, ISO created/updated timestamps, and explicit truncation/redaction
  flags. Non-matching child notes represented by gray search-redaction bars are not
  included at all, and no ancestor content is added merely for context. `@password`
  values are independently replaced before tool payloads enter model context or
  Agent Debug.
- Page text is additionally bounded by the configured total-page character budget,
  which is distributed across returned matching nodes so a large match set cannot
  create an unbounded Ollama prompt.
- The packaged base system prompt prefers Markdown final answers and explicitly permits LaTeX and fenced Mermaid diagrams when they improve clarity. A namespace-specific system-prompt override replaces that packaged text until `Restore packaged defaults` is selected.
- Chat transcript and activity-panel state live only in server memory, keyed by the opaque authenticated session token hash. Refreshing the browser with the same login rehydrates both; logout, password/auth reset, runtime lock purge, or server restart clears them.
- Transcript and streaming HTTP responses carry `Cache-Control: no-store`; the browser session request also explicitly bypasses its HTTP cache.
- A session permits one active generation at a time, keeps at most 100 messages, and bounds each user, thinking, and answer field to 32,000 characters.
- Failed turns remain visible in the transcript but are excluded from later Ollama prompt history.

## Agent Context and Debugging
- Canonical history contains only user messages and assistant-visible final-response prose; bracketed note-citation identifiers are removed from prior assistant messages before constructing a later Ollama request.
- Search results, loaded note text, structured actions, validation feedback, and temporary plans are working context for one run and are discarded afterward.
- Search skill text uses the same transient working-context boundary. It appears in
  the query-generation wire request and debug trace but is not carried into the
  later route call or future conversation history.
- Each run resolves the current namespace prompt overrides before constructing working context. Prompt settings never become canonical conversation history; the exact resolved prompt still appears inside every applicable outbound request in Agent Debug.
- The current/latest debug trace is always retained in session memory so the debugger can be opened after a bug. Starting another run replaces it.
- `Show exact prompts, model responses, and tool payloads` is checked by default and controls whether full JSON detail is rendered. It can be changed after the run; it does not control capture.
- The expandable outline includes one chronological `Ollama wire request` row for every model call: each route-selection attempt/retry, each Search-skill query attempt/retry, each later route selection after a tool result, and final-response synthesis. Each row shows the method, endpoint, and complete outbound JSON body, whose ordered `messages` array includes the literal user message and the exact system/transient context present for that call. Structured bodies are captured at the HTTP transport after Instructor's transformation, and Instructor exclusively owns the one visible retry. The outline also includes skill activation, raw structured responses, provider reasoning when returned, model settings/usage, policy decisions, tool arguments/results, timing, errors, and the final response.
- Exact-detail visibility can change during or after a run without clearing the trace. Logout, runtime lock, auth reset, and server restart clear the trace and reset the visibility toggle to on; Clear Chat clears the trace without changing the toggle.
- Traces are never written to SQLite, files, browser storage, or canonical conversation history.

See `docs/design/agent-harness.md` for runtime components, tool limits, and extension seams.

## Deferred Runtime Work
- A later phase may add an explicit-permission Ollama installer, configurable
  managed port, capability detection, a stop/restart control, and GPU/CPU-adaptive
  model recommendations.
- GPU is not a hard requirement. GPU-capable systems can offer larger models and context; CPU-only systems will recommend small quantized models, bound context aggressively, retain embeddings, and warn about slower generation.
