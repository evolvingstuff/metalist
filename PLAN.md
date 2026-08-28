# AI Chat and Managed Ollama Plan

## Objective

Add a first-class AI chat surface to MetaList, prove streamed Ollama connectivity and UI behavior without exposing note data, then replace the temporary user-managed connection with a MetaList-managed, local-only Ollama runtime.

## Product Boundaries

- Initial chat is standalone: no notes, search results, tags, attachments, reminders, or other MetaList data enter prompts.
- Chat history is plaintext in server memory only, scoped to the authenticated client session.
  - Survives browser refresh while the same auth session remains valid.
  - Clears on logout, session replacement/expiry followed by reauthentication, runtime lock purge, and server restart.
- Provider architecture is generic; Ollama is the first implementation.
- A GPU is an optional accelerator, never a setup or runtime requirement.
- Thinking-capable models stream a distinct reasoning section before/during the final answer.
- No implicit cloud fallback, remote-provider fallback, or background model download.
- Prompt, reasoning, completion, and embedding content must not be written to logs.

## Security Direction

The current branch began as an unmanaged connection/UI spike and defaults its configuration form to `http://127.0.0.1:11434`. That is not the final privacy boundary:

- MetaList does not own an existing process on port `11434`.
- A browser-supplied provider URL creates an unnecessary server-side request target.
- `OLLAMA_NO_CLOUD=1` disables Ollama cloud inference/search but does not prove OS-level no-egress isolation.

Approved target behavior should therefore be:

1. Preserve the chat UI, streamed-event contract, session store, and provider abstraction.
2. Treat user-managed Ollama only as a clearly labeled development/UI-spike mode.
3. Make the normal product path use only the endpoint produced by a MetaList-owned runtime object.
4. Remove `base_url` from browser chat/model requests once managed mode lands.
5. Never silently connect to `localhost:11434`, a remote Ollama host, or another provider.

## Multi-Namespace Ownership Decision

MetaList's top-level launcher exits after starting detached namespace servers, so it cannot safely own a long-lived Ollama child.

For the first managed iteration:

- Each namespace server lazily starts at most one Ollama child when its AI UI first requests models/chat.
- The namespace server owns that process for its lifetime and uses a dynamically selected loopback port.
- Lazy startup avoids launching one Ollama process for every namespace at normal MetaList startup.
- If users actively use AI in multiple namespaces, multiple managed Ollama processes may exist. Measure this before designing a shared runtime supervisor/broker.

A shared cross-namespace sidecar is deferred because it needs lease/refcount, crash recovery, endpoint publication, and ownership semantics that are substantially larger than the first AI integration.

## Phase 1 — Stabilize the Standalone Chat Spike

Status: implemented, verified with automated tests plus an isolated browser/Ollama smoke test, and accepted by the human for checkpointing.

### Backend

- Keep `app/services/ai_chat.py` as the token-fingerprint-scoped in-memory transcript store.
- Keep an explicit provider boundary around Ollama model discovery and streamed chat.
- Use typed NDJSON events:
  - `thinking_delta`
  - `content_delta`
  - `done`
  - `error`
- Accumulate thinking/content server-side during streaming so refresh restores the latest server state.
- Permit only one active generation per authenticated session.
- Cap prompt, thinking, response, and retained-message sizes.
- Clear chat state before token revocation and on decrypted-runtime purge.
- Classify Ollama/network/JSON failures as external; internal contract failures must still crash loudly.

### Frontend

- Add `AI agent settings…` and dynamic `Show/Hide AI chat` command-menu entries.
- Add the same chat toggle to the non-editing background/view context menu.
- Enabling chat atomically disables calendar view; enabling calendar atomically disables chat.
- Render a fixed right panel at one-third viewport width by default.
- Center/narrow notes, search, and view indicators inside the remaining left workspace.
- Add a drag boundary with a 280 px minimum and 60% viewport maximum.
- Render all model output as text, not raw HTML.
- Show streamed thinking in a distinct expandable section and the final answer separately.
- Include settings, clear-chat, close, multiline input, Enter-to-send, and Shift+Enter newline controls.
- Rehydrate the transcript from the server after refresh and after each completed/failed stream.
- Preserve usable dark-theme, narrow-window, focus, keyboard, and screen-reader behavior.

### Temporary Connection Guardrails

Until managed runtime replaces it:

- Label the configurable URL as an unmanaged Ollama connection.
- Restrict it to explicit loopback hosts (`127.0.0.1`, `[::1]`, or `localhost`), with HTTP allowed locally.
- Do not auto-claim that this mode is cloud-disabled or network-sandboxed.
- Do not send requests until the user opens settings/tests the connection or submits chat.
- Do not expose a general remote URL proxy.

## Phase 2 — MetaList-Managed Ollama Runtime

### Permission-Gated Ollama Installation

- Detect an existing compatible Ollama CLI first; installation is offered only when no usable executable is found.
- Never install, upgrade, replace, or uninstall Ollama automatically during MetaList startup, login, model selection, or inference.
- Show an in-app installation preflight containing:
  - detected OS and CPU architecture;
  - requested Ollama version/channel;
  - official download source;
  - approximate download and installed size when available;
  - destination and whether elevation/another installer UI is required;
  - the fact that installation/model acquisition temporarily requires network access.
- Require an explicit user action immediately before download/installer launch. A separate approval is required for later upgrades.
- Use only official Ollama distribution endpoints documented for the detected platform; do not use mirrors or package-manager substitutions silently.
- Prefer an app-private, versioned runtime under the MetaList data/runtime directory when Ollama publishes an appropriate standalone archive. This avoids requiring administrator access and avoids taking ownership of a user's system installation.
- Platform strategy:
  - Linux: prefer the official architecture-specific standalone archive over piping a remote script into a shell; avoid creating a systemd service because MetaList owns its inference child directly.
  - Windows: prefer the official standalone CLI archive for the managed runtime; the official interactive installer remains an explicit alternative when needed.
  - macOS: use the official supported distribution flow. If no documented standalone package is available, download/open the official installer only after approval, let the user complete installation, then rediscover the CLI.
- Download to an exclusively created temporary/version directory, verify an official signature/checksum when Ollama publishes one, validate archive/file type and architecture, then publish as a new version without overwriting another installed runtime.
- If no authoritative checksum/signature is available, make that limitation visible in the preflight and still require HTTPS, expected host/path validation, bounded size, and archive validation.
- Installation failure must leave the prior runtime untouched and report a clear retry/manual-install path.
- Never delete a user-managed Ollama installation or its models. Removal of a MetaList-private runtime, if added later, must target only the exact versioned directory MetaList created and require confirmation.
- Installing Ollama and downloading a model are separate workflows with separate size/network disclosures and permissions.
- After installation, start `ollama serve` only through the managed dynamic-port/cloud-disabled lifecycle below; do not rely on or terminate any desktop/background server the installer may also start.

Current official platform guidance is tracked from Ollama's macOS, Windows, and Linux documentation; exact URLs/commands must be resolved at implementation time rather than permanently hard-coded from this plan.

### Runtime Service

- Add `app/services/managed_ollama.py` containing the lifecycle/state model, separate from `OllamaProvider`.
- Maintain explicit runtime state including:
  - child/supervisor handle;
  - PID and process-group/job identity;
  - `127.0.0.1` host;
  - dynamically allocated port;
  - exact endpoint;
  - start timestamp;
  - readiness/status state.
- Locate the Ollama executable explicitly and report a clear unavailable state if missing.
- Resolve executable precedence explicitly: a selected MetaList-private runtime first, then a user-approved compatible system CLI; never silently replace one with the other during a running session.
- Ask the OS for a free loopback port, then launch without ever terminating the existing owner of another port.
- Construct a controlled child environment that forces:
  - `OLLAMA_NO_CLOUD=1`
  - `OLLAMA_HOST=127.0.0.1:<selected-port>`
- Preserve only environment values required for executable/library/platform operation; forced Ollama values always win.
- Start lazily and serialize concurrent startup attempts.
- Poll the exact managed endpoint with a bounded timeout before marking it ready.
- If the child exits during startup, surface bounded stderr/log output without prompts or model content.
- On unexpected exit/failed health check, fail closed and require explicit restart/retry; never fall back.

### Process Ownership and Shutdown

- Never call `pkill ollama`, `killall ollama`, `taskkill /IM ollama.exe`, or enumerate processes merely by name.
- macOS/Linux: create a MetaList-owned process group/session and terminate only that owned tree.
- Windows: use a Job Object or equivalent owned-tree boundary.
- Add a small ownership/supervision strategy so abnormal namespace-server exit does not intentionally leave an unmanaged child.
- FastAPI shutdown must:
  1. reject new generation work;
  2. cancel or bound-wait for in-flight work;
  3. request graceful child termination;
  4. bound-wait;
  5. force only the owned process tree if necessary;
  6. erase runtime endpoint/state.
- Runtime cleanup must verify stored ownership identity before signaling a PID, guarding against PID reuse.

### Provider/API Integration

- Construct `OllamaProvider` only from `ManagedOllama.endpoint`; no default endpoint in provider code.
- Remove `base_url` from browser `models` and `chat` request models.
- Add authenticated runtime endpoints/actions for status, start/retry, model listing, and stop if user control is desired.
- Keep provider methods transport-focused (`list_models`, `stream_chat`; later `embed`) and process management out of the provider.
- Do not persist the dynamically selected endpoint.

### Configuration UI

- Provider selector initially contains `Managed Ollama`; keep the structure extensible for future providers.
- Show runtime states: Not installed, Starting, Ready, Failed, Stopped.
- When Not installed, offer `Install Ollama…` and `Show manual instructions`; both preserve the explicit preflight/approval boundary.
- Show cloud-disabled and loopback-only facts accurately.
- Model selector lists already installed models from the managed runtime.
- Model acquisition is a separate explicit workflow; inference never downloads in the background.
- Show installation/runtime version and source (`MetaList-managed` or `System`) without implying that MetaList owns a system installation.
- Remove the editable URL from normal managed mode.
- If unmanaged/development mode remains, put it behind an explicit advanced choice with a privacy warning and loopback-only validation.

### Hardware Capability and Adaptive Profiles

- Add a runtime capability snapshot with explicit `gpu`, `cpu_only`, or `unknown` acceleration state; never infer “CPU only” merely because GPU detection failed.
- Detect capabilities after the managed runtime is ready and refresh them after a model loads when Ollama can report actual placement/VRAM usage.
- Keep detection provider/platform-specific behind a capability interface so higher-level chat logic consumes a normalized profile.
- Do not block setup, model discovery, chat, or future embeddings when no supported GPU is present.
- In `Auto` mode, derive conservative generation defaults from detected capability and selected-model metadata:
  - GPU available: permit larger recommended models, a larger bounded context, and richer/more iterative agent behavior.
  - CPU only: recommend small quantized models, apply an aggressively bounded context, keep embeddings enabled, and show an explicit slower-generation notice.
  - Unknown: use the CPU-safe bounded profile while labeling acceleration as unknown rather than making an unsupported hardware claim.
- Model recommendations should use available Ollama metadata such as parameter size and quantization, not model-name guessing alone.
- Keep context bounded in every profile; GPU availability raises a configured ceiling rather than creating an unbounded prompt window.
- Expose the active profile, detected acceleration, context ceiling, and performance warning in AI Agent Settings.
- Allow a future explicit advanced override, but validate it against hard memory/context safety caps and preserve fail-loud behavior for invalid values.
- Embeddings remain available under CPU-only operation; batching and concurrency should adapt separately from chat generation limits.

## Phase 3 — Optional Strong No-Egress Mode

- Treat this as a separate security feature, not an implication of `OLLAMA_NO_CLOUD=1`.
- Investigate platform-specific sandbox/firewall/container options that allow loopback but deny external egress for the managed Ollama tree.
- Define installation/model-download flow separately from inference so model acquisition can be explicitly network-enabled while inference remains blocked.
- Do not advertise “cannot access the network” until enforced and tested at the OS boundary on each supported platform.

## Testing Strategy

### Unit/Contract Tests

- Token/session isolation, refresh persistence, logout/reset cleanup, history caps, and concurrent-turn rejection.
- Ollama `/api/tags` parsing and `/api/chat` NDJSON parsing, including separate `message.thinking` and `message.content`.
- GPT-OSS thinking-level request behavior.
- Menu/context-menu labels and mutual calendar/chat exclusion.
- Resizer clamping and NDJSON incremental-buffer behavior.
- Client preferences encryption/validation while temporary unmanaged settings exist.
- Managed environment overrides, loopback-only host, dynamic port selection, readiness timeout, and no default endpoint.
- Capability normalization for GPU, CPU-only, and unknown states; Auto-profile model/context recommendations for each state.
- CPU-only chat and embedding paths remain enabled, with bounded context/concurrency and the required slower-generation notice.
- Process-tree ownership with fake Ollama executables; assert unrelated Ollama processes remain untouched.
- Installer platform/architecture selection, official-host allowlisting, size bounds, archive validation, exclusive versioned publication, cancellation, and rollback-on-failure.
- Assert startup/login/inference cannot trigger installation or upgrades without the explicit install action.
- Graceful stop, forced owned-tree stop, early child exit, port loss, and concurrent-start races.
- Logs contain lifecycle metadata only and never prompt/completion bodies.

### Integration/Manual Tests

- Start with Ollama absent and confirm clear configuration/runtime error.
- From Ollama-absent state, approve and complete installation on each supported platform; also cancel at preflight/download/installer handoff and verify no partial runtime becomes active.
- Test on GPU-accelerated, CPU-only, and capability-unknown hosts; verify setup is allowed in all three cases and recommendations/limits change appropriately.
- Run an unrelated user Ollama on `11434`; MetaList must leave it running and use a different port.
- Stream with a thinking-capable model and visually verify live reasoning/final-answer separation.
- Refresh without logging out and verify transcript restoration.
- Logout/re-login and verify transcript removal.
- Toggle calendar → chat → calendar and verify exclusive layout behavior.
- Drag panel through minimum/default/maximum widths and test intermediate/narrow windows.
- Stop/crash the managed child and confirm no cloud/default-host fallback.
- Shut down MetaList and verify only MetaList-owned processes terminate.
- Repeat lifecycle tests on macOS, Linux, and Windows before declaring cross-platform support.

## Documentation

- Add `docs/ui/ai-chat.md` for UI, state lifetime, thinking display, no-note-data boundary, and troubleshooting.
- Update `docs/ui/activity-calendar.md`, `docs/ui/command-palette.md`, and `docs/ui/controls.md` for exclusive RHS views.
- Add `docs/security/managed-ollama.md` for process ownership, loopback/cloud/no-egress claims, model acquisition, logging, and failure behavior.
- Update `docs/AI-SUMMARY.md` after implementation stabilizes.

## Completion Criteria

### Standalone UI Spike

- Chat/configuration UI works against an explicitly selected loopback Ollama instance.
- Thinking and answers stream separately.
- Transcript survives refresh in the same authenticated session and clears at the required boundaries.
- Calendar and chat never display simultaneously.
- Relevant Python, Node, template, startup-sanity, and full test suites pass.
- Human testing confirms the UI and a real Ollama connection before any commit.

### Managed Runtime

- MetaList launches its own `ollama serve` lazily on a dynamic loopback-only port.
- If Ollama is absent, MetaList can install an official compatible runtime only after explicit user permission; no install or upgrade occurs implicitly.
- `OLLAMA_NO_CLOUD=1` and exact `OLLAMA_HOST` are forced.
- All inference/model calls use only the endpoint in the owned runtime object.
- Port `11434` and unrelated Ollama processes are untouched.
- Readiness is bounded and failures remain local/explicit with no fallback.
- Shutdown terminates only the owned process tree.
- Security messaging distinguishes cloud-disabled from OS-enforced no-egress.
- GPU acceleration is optional; CPU-only mode keeps chat and embeddings functional with conservative limits and visible performance guidance.
