# AI Chat (Phase 1)

## Scope
- MetaList can chat directly with an Ollama model through an authenticated server endpoint.
- This first phase is deliberately standalone: note content, tags, search results, and other MetaList data are never added to prompts.
- The current provider connection is labeled **temporary unmanaged Ollama**. MetaList can ask that process to download a model, but does not install, start, stop, or own the Ollama process yet.

## Configuration
- Open `AI Agent Settings…` from the command palette or use the gear button in the chat header to configure the Ollama connection, view downloaded models, and save a selected model. The chat composer also provides immediate model and thinking-level selection beside Send.
- Ollama is the only provider in Phase 1; the provider field is present so future providers can share the same configuration surface.
- The server accepts only explicit loopback base URLs: `localhost`, `127.0.0.1`, or `[::1]`, over HTTP or HTTPS. `localhost` is canonicalized to `127.0.0.1`, environment proxy settings are ignored, and redirects are not followed. Credentials, query strings, fragments, and non-root paths are rejected (`/api` is normalized to the root URL).
- Opening the chat panel asks Ollama for its installed models so the composer selector is current. Saving a changed connection URL refreshes that list.
- AI Agent Settings loads the models already downloaded in the displayed Ollama instance. Save persists the displayed connection and the explicitly selected downloaded model. Download is a separate action: the user chooses the exact name from the linked official Ollama library and explicitly starts the pull. MetaList does not scrape the library or depend on an undocumented catalog API. Status and byte progress stream from Ollama's supported `/api/pull` endpoint; success refreshes the downloaded-model list without selecting or saving the new model.
- Provider URL, selected model, and thinking level are namespace-scoped client preferences. In a password-protected namespace they use the existing encrypted client-state persistence path.
- The compact selectors immediately left of Send choose the model and show `Thinking Off`, `Low Thinking`, `Medium Thinking`, or `High Thinking`, with Low as the default. Changes persist immediately. MetaList sends native Ollama `think: false` for Thinking Off and the corresponding level string otherwise. Model support varies; GPT-OSS supports Low/Medium/High but cannot disable thinking, so Thinking Off is unavailable for GPT-OSS selections.

## Panel Behavior
- `Show/Hide AI Chat` is available from the command palette and from the notes-view right-click menu outside edit mode.
- AI chat and the right-side activity calendar are mutually exclusive. Enabling either view atomically disables the other preference.
- The panel occupies the right third of the viewport by default. The notes shell narrows into the remaining space instead of being covered.
- Drag the panel's left separator to resize it. Chat remains at least 280 px wide and leaves at least 480 px for the notes area. The focused separator also supports Left/Right Arrow plus Home/End. The chosen width is saved as a client preference, restored after refresh, and temporarily clamped when the viewport is too narrow without replacing the saved preference.
- The header provides clear, settings, and close actions. `Enter` sends; `Shift+Enter` inserts a newline.
- Dragging the message field's lower-right resize handle saves its height as a client preference and restores it after refresh.
- While the current response is streaming, the composer remains editable so the next message can be drafted. Send, model selection, thinking-level selection, and transcript clearing remain disabled until that response finishes.
- Right-click a completed assistant response and choose `Copy Response` to copy it as a MetaList note payload. The raw response Markdown is preserved and automatically tagged `@markdown @llm`; the system clipboard receives rendered rich HTML plus the raw Markdown as plain text. The copied response can be pasted as a sibling or child note, but reference-paste actions remain unavailable until it exists as a real MetaList note with its own UUID.

## Streaming and Session State
- `/api2/ai/chat` streams typed NDJSON events: `thinking_delta`, `content_delta`, `done`, or `error`. The endpoint explicitly bypasses response compression and proxy buffering so small answer tokens reach the browser immediately rather than collecting until completion.
- Thinking and answer content render separately. While waiting, the panel animates `Thinking…` and shows elapsed seconds without a misleading disclosure arrow. Thinking and answer events each include a cumulative server-rendered snapshot, so Markdown and completed LaTeX expressions format while text is still streaming. An open reasoning disclosure collapses when the first answer chunk arrives. The user can reopen it afterward, and that explicit choice is preserved while later answer chunks render. Mermaid source is finalized into a diagram when the turn completes. Models that do not emit reasoning cannot provide substantive intermediate text before their first answer token.
- Assistant thinking and answers use MetaList's Markdown renderer while streaming, including completed LaTeX delimiters rendered as MathML. Fenced `mermaid` diagrams are rendered by the strict local Mermaid runtime after completion.
- Chat transcript state lives only in server memory, keyed by the opaque authenticated session token hash. Refreshing the browser with the same login rehydrates the transcript; logout, password/auth reset, runtime lock purge, or server restart clears it.
- Transcript and streaming HTTP responses carry `Cache-Control: no-store`; the browser session request also explicitly bypasses its HTTP cache.
- A session permits one active generation at a time, keeps at most 100 messages, and bounds each user, thinking, and answer field to 32,000 characters.
- Failed turns remain visible in the transcript but are excluded from later Ollama prompt history.

## Planned Managed Runtime
- A later phase will add an explicit-permission Ollama installer and a MetaList-owned local process with dynamic loopback binding, cloud features disabled, capability detection, and GPU/CPU-adaptive model recommendations.
- GPU is not a hard requirement. GPU-capable systems can offer larger models and context; CPU-only systems will recommend small quantized models, bound context aggressively, retain embeddings, and warn about slower generation.
