# Agent Harness: Read-only Foundation

## Current Scope

- MetaList owns the orchestration loop; the HTTP route does not call Ollama directly.
- Instructor owns every JSON/Pydantic action-selection call over Ollama. Natural-language final synthesis streams through the direct Ollama adapter.
- LiteLLM, skills, remote providers, and note mutations are deferred.
- One user-selected model handles action selection and final synthesis through an explicit model-policy seam.
- Internal actions are a closed Pydantic discriminated union: `search_notes`, `read_notes`, `respond`.
- Ollama receives a flat, fully required Pydantic envelope instead of a root `oneOf` schema. `kind` alone selects the action; inactive required fields are placeholders and are ignored when the envelope is projected into the strict internal union. The prompt still requests empty placeholder values to keep traces clear.
- Search/read tools use the hydrated in-memory `SearchIndex` and `NoteStore`; agent reads never query SQLite.
- The existing `/api2/ai/chat` NDJSON contract remains the user-facing streaming boundary.

## Runtime Flow

```text
POST /api2/ai/chat
  → AiChatSessionStore.start_turn
  → AgentRuntime
      → ContextBuilder(system prompt + canonical conversation)
      → Instructor + Ollama typed action call (non-streaming)
      → Pydantic validation; Instructor performs one schema-guided retry if invalid
      → PermissionPolicy
      → search_notes/read_notes tool
      → append transient action + tool result
      → repeat or select respond
      → Ollama final synthesis (streaming)
  → AiChatSessionStore.complete_turn
```

The model receives the flat action envelope through Instructor `JSON_SCHEMA` mode on Ollama's OpenAI-compatible endpoint. Instructor places the Pydantic schema in `response_format`, so Ollama constrains generation to the schema before Instructor performs Pydantic validation. MetaList does not duplicate the serialized schema in its system prompt. Tool mode remains excluded because some nominally tool-capable local models return JSON content instead of a tool call, which breaks tool-mode parsing/reasking. The flat wire shape avoids root-union/reference compatibility failures without weakening the internal action types. Only fields active for the selected `kind` are semantically validated, preventing irrelevant placeholder content from rejecting an otherwise safe action. Internal action calls use temperature `0` and allow one Instructor retry. Final synthesis retains the selected thinking level and streams thinking/content through the existing UI.

Harness rule: if a model call must return JSON/Pydantic data, it goes through Instructor. If a model call returns natural-language streaming output, it goes through the provider adapter directly. LiteLLM can be introduced behind the same inference seam when multiple providers, routing, fallbacks, or cost accounting are actually required.

## State Boundaries

### Canonical conversation

- User messages and completed assistant-visible answers only.
- Failed turns are excluded from later model context.
- Provider reasoning, actions, searches, note payloads, and validation retries never enter later turns.

### Working context

- System prompt, structured actions, tool results, and final-response instruction for one run.
- Built append-only during the active run and discarded when it ends.
- Future skill content must be appended here as a versioned event; it must not be inserted into old prompt tokens or copied into canonical history.

### Debug trace

- The latest trace is always captured in session memory so a completed or failed run can be inspected after the fact.
- Only the current or most recently completed run exists; starting a new run replaces the previous trace.
- Instructor hook states are appended live while a call is running: attempt start, Ollama response received, validation, retry/final failure, and success. Exact transformed model requests, every retry response/error, schemas, provider reasoning, usage, policy decisions, tool arguments/results, timing, final response, and errors are captured.
- Every call to Ollama appends its own `OLLAMA_REQUEST` entry before the response: each Instructor action-selection attempt (including retries and later post-tool selections) and the direct final-response stream. The entry contains the HTTP method, endpoint, and complete JSON body with the ordered messages used at that moment, including canonical user messages and transient tool/final-response instructions. Structured bodies are captured from the HTTP transport after Instructor adds the native `json_schema` response format; the OpenAI-compatible transport does not perform hidden retries.
- The debugger does not substitute a standalone system-prompt entry for a request. The system prompt appears in its real position inside each outbound request's `body.messages` array alongside the corresponding user message.
- Logout, runtime lock, auth reset, or process restart clears the trace and resets exact-detail visibility. Clear Chat removes the trace while preserving the current visibility toggle.
- No trace rows or payloads are persisted to SQLite, files, browser storage, or canonical conversation history.

## Read-only Tools

### `search_notes`

- Uses normal MetaList search syntax: tags are unquoted, text is quoted, `-` excludes, uppercase `OR` separates clauses.
- Invalid syntax fails Pydantic action validation and receives the single structured-output retry.
- Returns at most 20 results in note-store order with UUID, parent UUID, tags, and a 400-character plain-text preview.

### `read_notes`

- Accepts 1–12 unique note UUIDs.
- Returns plain text and tags from the in-memory store.
- Bounds each note to 12,000 characters and each call to 60,000 returned characters.
- Reports missing, omitted, and truncated notes explicitly.

No create, edit, move, trash, delete, SQL, filesystem, or shell action exists in the action schema or tool registry.

## UI

- Live `action_status` events append compact activity panels to the assistant turn instead of replacing one status line. Panels distinguish model waits/validation, Instructor retries, note search/read tools, and final-response writing with different tinted backgrounds. They remain in the session transcript but never enter canonical model history.
- Each structured call reports its current attempt and maximum attempt count. Validation/provider failures identify the failure type and whether Instructor will retry; the exact error remains available in the debug trace.
- Exhausted structured retries produce a short user-facing error panel that directs the user to Agent Debug; Instructor's full exception and attempt payloads are not dumped into the chat.
- The `Thinking` disclosure renders only when the selected model actually emits reasoning content. Thinking Off therefore never shows a misleading `Thinking` heading.
- The chat-header trace button opens a large debugger modal.
- `Show exact prompts, model responses, and tool payloads` controls detail visibility and can be changed before, during, or after a run. It never controls whether the latest trace is retained.
- The debugger renders the latest run as a chronological expandable outline. Enabling exact details exposes each row's full JSON payload.

## Main Files

- Runtime: `app/services/agent/runtime.py`
- Actions: `app/services/agent/actions.py`
- Prompt/context: `app/services/agent/context.py`
- Model policy: `app/services/agent/model_policy.py`
- Permissions/tools: `app/services/agent/permissions.py`, `app/services/agent/tools.py`
- Transient trace: `app/services/agent/trace.py`
- Ollama seam: `app/services/agent/ollama_inference.py`, `app/services/ollama_provider.py`
- API: `app/api/routes/ai.py`
- Debug UI: `app/static/js/modules/ai-chat/ai-agent-debug-view.js`
- Tests: `tests/unit/test_agent_runtime.py`, `tests/unit/test_ai_chat.py`, `tests/unit/test_ai_routes.py`

## Deferred Seams

- LiteLLM can replace or wrap `OllamaInferenceAdapter` without changing the runtime/tools.
- LiteLLM can wrap Instructor at the inference seam when multiple providers, routing, fallbacks, or cost accounting justify the additional layer.
- Model routing can extend `SingleModelPolicy` at explicit inference-purpose boundaries.
- Skills can be loaded as append-only, versioned working-context events and represented in the same trace outline.
- Mutations require new action types, tool specs, permission decisions, confirmation UX, and regression tests; they must not be added by widening the current read-only handlers.
