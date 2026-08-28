# AI Chat (Phase 1)

## Scope
- MetaList can chat directly with an Ollama model through an authenticated server endpoint.
- This first phase is deliberately standalone: note content, tags, search results, and other MetaList data are never added to prompts.
- The current provider connection is labeled **temporary unmanaged Ollama**. MetaList does not install, start, stop, or own the Ollama process yet.

## Configuration
- Open `AI Agent Settings…` from the command palette or use the gear button in the chat header.
- Ollama is the only provider in Phase 1; the provider field is present so future providers can share the same configuration surface.
- The server accepts only explicit loopback base URLs: `localhost`, `127.0.0.1`, or `[::1]`, over HTTP or HTTPS. `localhost` is canonicalized to `127.0.0.1`, environment proxy settings are ignored, and redirects are not followed. Credentials, query strings, fragments, and non-root paths are rejected (`/api` is normalized to the root URL).
- Opening settings or pressing `Refresh` asks Ollama for its installed models. MetaList makes no Ollama request before the user opens settings or submits a chat message.
- Provider URL and selected model are namespace-scoped client preferences. In a password-protected namespace they use the existing encrypted client-state persistence path.

## Panel Behavior
- `Show/Hide AI Chat` is available from the command palette and from the notes-view right-click menu outside edit mode.
- AI chat and the right-side activity calendar are mutually exclusive. Enabling either view atomically disables the other preference.
- The panel occupies the right third of the viewport by default. The notes shell narrows into the remaining space instead of being covered.
- Drag the panel's left separator to resize it. Chat remains at least 280 px wide and leaves at least 480 px for the notes area. The focused separator also supports Left/Right Arrow plus Home/End. Width is browser-memory-only and resets on refresh.
- The header provides clear, settings, and close actions. `Enter` sends; `Shift+Enter` inserts a newline.

## Streaming and Session State
- `/api2/ai/chat` streams typed NDJSON events: `thinking_delta`, `content_delta`, `done`, or `error`.
- Thinking and answer content render separately. The thinking disclosure remains open during generation and collapses when the response completes.
- Chat transcript state lives only in server memory, keyed by the opaque authenticated session token hash. Refreshing the browser with the same login rehydrates the transcript; logout, password/auth reset, runtime lock purge, or server restart clears it.
- Transcript and streaming HTTP responses carry `Cache-Control: no-store`; the browser session request also explicitly bypasses its HTTP cache.
- A session permits one active generation at a time, keeps at most 100 messages, and bounds each user, thinking, and answer field to 32,000 characters.
- Failed turns remain visible in the transcript but are excluded from later Ollama prompt history.

## Planned Managed Runtime
- A later phase will add an explicit-permission Ollama installer and a MetaList-owned local process with dynamic loopback binding, cloud features disabled, capability detection, and GPU/CPU-adaptive model recommendations.
- GPU is not a hard requirement. GPU-capable systems can offer larger models and context; CPU-only systems will recommend small quantized models, bound context aggressively, retain embeddings, and warn about slower generation.
