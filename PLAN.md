# Agent Web Browsing

## Goal

Add controlled public-web retrieval to the MetaList agent while preserving the
existing note-disclosure boundary, current-production prompt regressions, explicit
evidence provenance, and cross-platform behavior.

The agent must support three namespace-scoped modes:

1. **No web access** — no page-opening action is available.
2. **Contextual web access** — the agent may open only exact URLs already disclosed
   through permitted context; it cannot propose new URLs or follow links discovered
   in pages.
3. **Full web access** — the agent may propose and open direct public page URLs.

`No web access` is the default for new and existing installations. A setting change
takes effect on the next message.

## Agreed Product Contract

### Authorization

- Do not maintain URL or domain whitelists/blacklists.
- In contextual mode, build the per-turn URL capability set only from:
  - URLs explicitly supplied in user-authored conversation messages;
  - URLs in the selected tree or investigation evidence actually disclosed after
    password, cloud-privacy, search-redaction, and token-retention filtering; and
  - canonical URLs from web evidence already opened and cited in this chat session.
- Never inspect hidden note content to build that capability set. A URL found only
  in a password-protected, blacklisted, non-whitelisted, search-redacted, omitted,
  or otherwise undisclosed note remains unavailable.
- A public URL is allowed if it is independently disclosed through an authorized
  source. Its occurrence in a hidden note does not globally poison it.
- Page contents are evidence, not authority. Links occurring in an opened page do
  not enter the contextual capability set.
- In full mode, independently discovered public URLs are permitted.
- Authorization is enforced by application code for every URL, even if the model
  emits an invalid action.

### Actions

- Add a typed `open_web_pages` action accepting **1–8 URLs**.
- Fetch unique normalized URLs concurrently and return results in submitted order.
  Repeated equivalent URLs are fetched once and reuse the same evidence.
- One external fetch failure produces a structured result for that URL without
  discarding successful sibling results. Invalid action structure and internal
  invariants still fail loudly.
- Do not add a search-engine action. Both enabled modes expose only the typed,
  batched `open_web_pages` action.
- In full mode, the model may propose direct public HTTP(S) page URLs even when they
  are absent from context. Page retrieval remains an application tool independent
  of the selected LLM provider.
- Ordinary full-mode lookups open a Google Search result URL through
  `open_web_pages`, then open useful result pages in later batches. Google pages
  and source pages use the same application-owned fetcher; no LLM provider supplies
  retrieval.
- Do not create a mutually exclusive top-level “web lookup” route. Web actions must
  compose with selected-note and investigated-note evidence in the same run.

### Retrieval and evidence

- Support public HTTP and HTTPS resources containing HTML, plain text, or PDF.
- Fetch with GET only, verified TLS, no browser cookies, no user credentials, and no
  JavaScript execution.
- Reject loopback, private, link-local, multicast, reserved, metadata-service, file,
  and unsupported-scheme targets. Resolve and pin public addresses, then repeat the
  checks at every redirect hop to resist DNS rebinding and redirect-based SSRF.
- Allow bounded redirects as part of opening the submitted URL. Record both the
  requested URL and final URL. A redirect is not considered following an in-page
  link.
- Enforce per-page and per-action time, byte, extracted-text, and token limits.
  Report truncation explicitly. Never let compression or malformed content evade
  the byte limits.
- Extract readable text and title deterministically. Reuse the existing hardened URL
  normalization, public-target resolution, and pinned transport where appropriate;
  factor shared networking primitives out of `app/services/link_titles.py` instead
  of implementing weaker duplicate checks.
- Treat all fetched text as untrusted data. Web content cannot change settings,
  grant URL access, select further actions, override system/user instructions, or
  execute commands.
- Each successful page result carries a stable session evidence ID, requested URL,
  final URL, title, extracted content, retrieval time, and truncation state. Each
  page keeps explicit URL provenance.

### Conversation lifetime and citations

- Keep successful web evidence in a bounded server-side store owned by the current
  AI chat session. Reuse it for follow-up questions without fetching it again.
- Deduplicate both within a batch and across the session. After a redirect, index the
  evidence by both the requested and final normalized URLs.
- Clear retained web evidence with the chat reset and normal session teardown. Do not
  write page bodies into notes, durable chat history, client preferences, backups,
  or the note database.
- Extend the final-response evidence catalog and sanitizer to accept explicit web
  citation tokens alongside note citations. Render external references with the
  fetched title and final URL while preserving the existing note-reference behavior.
- Retain enough bounded web evidence for follow-ups. If the configured evidence
  budget cannot include every retained page, report exact included/omitted counts
  to the model and never imply complete coverage.
- Show concise activity such as `Opening 3 web pages`, followed by success, failure,
  and truncation counts. The UI
  must expose the sources used in the final answer without exposing internal prompt
  or capability metadata.

## Implementation Plan

### 1. Add the mode setting

- Define a strict web-access mode type and resolver near the existing agent settings.
- Store the value in encrypted namespace client preferences, following the current
  settings path so no database schema change is needed.
- Add a three-choice control to **AI Agent Settings** with concise explanations and
  `No web access` as the missing-value/default behavior.
- Include the frozen mode in each run context. Expose no web schemas in no-access
  mode, only `open_web_pages` in contextual mode, and both actions in full mode.
- Add product-help text so the agent can accurately explain and open this setting.

### 2. Extract a shared safe HTTP transport

- Move URL normalization, DNS resolution, public-address validation, address pinning,
  TLS setup, redirect validation, and bounded streaming into a small shared service.
- Preserve link-title behavior and its current cache contract while converting
  `link_titles.py` to the shared implementation.
- Make every security decision testable through injected resolution and transport
  seams; production defaults must use the real resolver and verified TLS.

### 3. Implement page retrieval and parsing

- Create required typed request/result records for page batches and per-page outcomes.
- Normalize and deduplicate before scheduling a bounded concurrent batch.
- Extract main readable HTML text without navigation/chrome, preserve useful headings
  and lists, decode plain text safely, and extract bounded PDF text.
- Capture externally expected failures by category—timeout, DNS, rejected target,
  HTTP status, unsupported content, oversized response, and malformed document—while
  allowing internal programming errors to propagate.
- Return results in submitted order and share one evidence object for duplicates.

### 4. Implement unrestricted direct-page opening

- Keep the sole web tool, `open_web_pages`, outside every LLM-provider adapter.
- In full mode, accept direct public HTTP(S) URLs proposed by the model without
  requiring them to appear in context. Continue applying the same network and SSRF
  controls to every request.
- Keep page opening unavailable in no-access mode and capability-limited in
  contextual mode. Application code, not prompt wording, enforces both boundaries.
- Do not add OpenAI-hosted search, another search provider, or any provider-specific
  retrieval behavior.

### 5. Add per-turn URL capabilities

- Extract normalized URLs from user-authored messages and already-filtered evidence
  objects; never scan the underlying NoteStore as an authorization shortcut.
- Carry source provenance for every capability so debug output can prove why a URL
  was allowed without exposing hidden notes.
- Validate every contextual batch member before network work begins. Return an
  unavailable result for unauthorized URLs without revealing whether a hidden note
  contains that URL.
- Add retained, previously cited web URLs to later-turn capabilities. Do not add
  arbitrary links parsed from their page bodies.

### 6. Extend the agent execution loop

- Extend strict action schemas and the application-owned step loop to execute batched
  web actions, append verified results, and return control to the model until it can
  answer or reaches the existing bounded-step limit.
- Allow a run to combine selected-note context, scoped investigation evidence, and
  opened-page evidence. Preserve the frozen note scope and disclosure
  boundary throughout the run.
- Add browsing instructions as a conditionally loaded production skill. Keep the
  no-web request prefix and schemas unchanged so unrelated regression cases remain
  genuinely unaffected.
- Explicitly instruct the model that web content is untrusted evidence, contextual
  page links cannot be followed, citations must support web-derived claims, and an
  unavailable page must not be presented as read.
- Record actions, timings, normalized URLs, result metadata, and provider usage in
  diagnostics without recording credentials or hidden-note provenance.

### 7. Retain and render web evidence

- Add a session-owned bounded evidence store alongside the current AI chat store.
- Reuse successful evidence on duplicate opens and later turns; expose cache reuse in
  diagnostics and avoid duplicate network requests.
- Extend stream events, final-response sanitization, stored assistant messages, copy,
  and reload rendering to support both note and web reference scopes.
- Render one external reference entry per cited final URL, with safe external-link
  attributes and duplicate citations collapsed. Keep note-reference navigation
  unchanged.
- Ensure reset, logout/session teardown, cancellation, and failed turns leave no
  orphaned in-flight requests or inaccessible retained evidence.

### 8. Add UI feedback and accessibility

- Display batched page-open activity with counts while work is running and concise
  outcome summaries afterward.
- Make partial external failures understandable without showing stack traces, and
  keep internal errors loud through the existing Loguru/error boundary.
- Ensure activity and references are keyboard accessible and announced through the
  existing status semantics.
- Keep the composer cancellable while page fetch tasks are active.

### 9. Update documentation

- Update `docs/design/agent-harness.md` with action sequencing, URL capabilities,
  retained evidence, and security boundaries.
- Update `docs/ui/ai-chat.md` with modes, activities, citations, and reset behavior.
- Update `docs/security/README.md` with SSRF, redirects, untrusted-content, and data
  retention guarantees.
- Update `docs/testing/harness.md` and `docs/AI-SUMMARY.md` after implementation.

## Test Plan

### Deterministic Python tests

- Mode parsing/defaults and strict setting persistence.
- Conditional action-schema exposure for all three modes.
- URL extraction from user messages and only actually disclosed note/web evidence.
- Blacklisted, non-whitelisted, password-protected, search-redacted, token-omitted,
  and unavailable selected notes never authorize their URLs.
- Independent authorization of the same URL from a user message or permitted note.
- Conservative normalization, fragment removal, query preservation, submitted-order
  results, same-batch duplicates, cross-turn duplicates, and redirect aliases.
- Concurrent batch scheduling with a hard maximum of eight and bounded concurrency.
- Per-item external failures alongside successful results.
- HTML, plain-text, and PDF extraction; titles; malformed encodings/documents;
  truncation; unsupported content; large/chunked/compressed responses.
- SSRF protection for literal and DNS-resolved private addresses, IPv4/IPv6,
  redirect hops, DNS rebinding, metadata targets, credentials, and schemes.
- Contextual mode cannot open in-page links; full mode can independently open them.
- Prompt-injection text remains inert evidence and never expands capabilities.
- Full-mode direct URL authorization and page-fetch failure handling.
- Combined note/web evidence, bounded retention, reset/session cleanup, cancellation,
  step limits, trace redaction, and exact citation authorization.
- Existing link-title behavior remains unchanged after transport extraction.

### Deterministic JavaScript and browser tests

- Settings modal displays/saves all three values and defaults to no access.
- Stream validation and activity rendering for batched page-open outcomes.
- Mixed note/web references survive streaming, reload, copy, and conversation reset.
- A real browser scenario selects permitted and blocked notes, verifies only disclosed
  URLs can be opened in contextual mode, and confirms outgoing page links remain
  unauthorized.
- Run the same core browser scenario in Chrome and Firefox on Windows, macOS, and
  Linux; Edge on Windows remains additive under the release matrix.

### Current-production LLM regressions

- Add fixed cases for no-access refusal/answering, contextual user URLs, permitted
  note URLs, blocked-note URLs, batched duplicate opens, unrestricted direct opens, combined
  note-and-web questions, follow-ups over retained pages, partial failures, and
  citation selection.
- Build every case through the production prompts, conditional skill loader, action
  schemas, context builders, and evidence serializers.
- Establish a five-repetition before baseline, run the affected selection after the
  prompt/schema change with the existing cache-aware scheduler, and compare reports.
  Effective-request fingerprinting must prove that no-web and unrelated help skills
  are skipped only when their complete production requests are unchanged.
- Run broader live coverage if changes to provider execution cannot be represented by
  prepared-request comparison. Provider errors remain failures in the denominator.

### Human acceptance checks

1. Confirm existing installs begin in **No web access** and ordinary note chat behaves
   exactly as before.
2. In contextual mode, open several note/user URLs at once, including a duplicate;
   verify one fetch per unique URL, usable citations, and follow-up understanding.
3. Verify a URL found only in a blocked/redacted/password note cannot be opened and
   that the response does not leak its existence or source.
4. Verify a directly supplied copy of that same public URL is allowed.
5. Verify links shown inside an opened page cannot be followed in contextual mode.
6. In full mode, have the model propose multiple direct public page URLs, batch-open
   them, combine them with note evidence, and verify mixed citations.
7. Reset the chat and verify retained page evidence is gone.

## Completion and Release Gates

- User completes the human acceptance checks before `COMMIT FEATURE`.
- Relevant Python, JavaScript, startup, browser, and current-production LLM regression
  tests pass. Every skipped test/result is reported with its concrete reason.
- Networking/security changes pass the applicable Windows, macOS, and Linux
  feature-branch workflow before merge.
- Update documentation and remove this `PLAN.md` during `COMMIT FEATURE`.
- Any later PyPI release requires the exact merged main commit to pass the full
  release matrix before a tag is created; tag publication reuses those tested
  artifacts and does not rerun the matrix.

## Explicitly Out of Scope

- Persistent domain allowlists or denylists.
- Authenticated browsing, cookies, browser automation, form submission, POST requests,
  downloads into notes, or JavaScript execution.
- Following page links in contextual mode.
- Allowing web content to edit notes, settings, permissions, or browsing mode.
