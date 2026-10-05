# PLAN: Replace AI chat routing with a tool-using agent

Branch: `feature/agent-error-messages` (contains the committed failure-explanation
checkpoint); the redesign continues here unless you prefer a fresh branch.

## Why

Every chat message today starts with one structured call that must pick exactly
one of five routes (`respond`, `investigate_current_scope`,
`summarize_current_scope`, `tag_proposals`, `metalist_help`). Capabilities are
tied to the route, so requests that need two of them fail or get half-answers
(the reported "What's new in 0.11.0? Check GitHub" question needs product help
*and* the web; help can never browse). Ambiguous requests flip between routes
from run to run (measured: 3/5 vs 2/5). Several custom JSON formats carry
cross-field rules that are only described in prose and enforced afterwards,
which turns model slips into red errors.

## Decisions already made (you)

1. **Tool-using agent**: no up-front route. The model calls tools as needed,
   in any order, then answers.
2. **Note changes are proposed by the agent and confirmed by you** in a Yes/No
   box. Nothing changes without an explicit Yes.
3. **Provider-neutral**: nothing in the design may depend on OpenAI; Claude may
   replace it. Provider specifics live in one adapter.
4. **Default tool order** when there is no dependency between tools, so runs are
   comparable and testable; a tool may run earlier only when another tool needs
   its result.
5. **Live-LLM tests for every capability**, with thinking modes on (Low, Medium,
   High), not only Off.

## Design principles

- One simple, self-contained argument format per tool: no field whose validity
  depends on another field. Rules are explained in the tool description *and*
  made unrepresentable in the schema; our validation stays as a safety net.
- Strict schema enforcement is used where a provider supports it, as an adapter
  setting, never as a design dependency.
- Tools only read through the frozen view snapshot (`ScopedSearchSnapshot`) and
  the privacy boundary, never the global search index (the old `tools.py`
  search ignores both and must not be reused).
- Model misbehaviour is an expected external failure: a bad tool call is
  explained back to the model once; if it persists, the agent answers with the
  limitation instead of a red error, and the failure explanation (already built)
  records what happened.
- Internal defects still fail fast and loud.

## Default tool order

1. MetaList help lookup
2. Notes in your current view (overview → search/read)
3. Web
4. Proposing a change (tags) or a large operation (whole-view summary)

Allowed dependencies (documented in the instructions and in tests): a web page
whose address came from a note; reading notes found by a search; proposing tags
after reading the notes they concern. Any other deviation counts as a test
failure.

## Tools (first set)

| Tool | Arguments (independent) | Notes |
| --- | --- | --- |
| `lookup_metalist_help` | `topics` (list of known topic ids) | Returns the help skill texts. Adds a packaged **release notes** source (from README "Changes in x.y.z") so "what's new" works without the web. |
| `view_overview` | none | Scope label, counts, selected note tree (as today's SELECTED_NOTE_CONTEXT). |
| `read_view_notes` | `root_ids` (optional list; empty = as many whole trees as fit the budget) | Today's investigation payload, from the frozen snapshot, within the evidence budget. |
| `search_view_notes` | `query` | Search **within the frozen view only**, privacy-filtered; returns matching trees within budget. |
| `open_web_pages` | `urls` | Existing fetcher, SSRF protection, evidence store and citation tokens; modes none/contextual/full unchanged. In full mode, addresses that contain text you did not type yourself (e.g. an address suggested by a web page) are shown in a Yes/No box before opening, against prompt injection. |
| `open_menu` | `menu_id` | Opens without asking, as today: opening changes nothing, palette entries are only highlighted, and destructive dialogs carry their own safeguards (e.g. typing the namespace name). |
| `summarize_view` | none | Existing staged summary (batches, citations, reduction); keeps its confirmation card. |
| `propose_tag_operation` | `action` (generate/accept/remove), `scope` (current view/namespace), `tag_filter` | **Never executes by itself**: the app shows a Yes/No box with exactly what will change (counts, tags); only Yes applies. Generation keeps its scope/focus card. |

The final answer is streamed as plain text after the tool calls, with citations
to the notes and web pages the tools returned.

## Phases

### Phase 1 — Provider-neutral tool calling
- Extend the `InferenceAdapter` interface with a tool-calling turn: messages that
  can hold tool calls and tool results; tool definitions as Pydantic models →
  JSON schema. Keep the interface free of OpenAI types.
- OpenAI adapter: native function calling (strict where supported), reasoning
  effort, usage/cost, exact request capture for Agent Debug and history export.
- Update everything that assumes `{role, content}`-only messages (token
  estimation, context validation, history/trace export) to accept tool messages.
- A scripted fake adapter for unit tests.
- Instructor stays for the remaining single-answer steps (summary batches, tag
  batches).

### Phase 2 — Tools
- Implement the tools above on the frozen snapshot and privacy boundary, each
  with unit tests (budgets, privacy exclusion, invalid arguments, empty results).
- Release notes packaged for `lookup_metalist_help` (README "Changes in x.y.z"
  sections).
- Close web gaps found in the survey: re-check contextual-mode capability after
  redirects; in full mode, detect addresses containing text not typed by the user
  and require confirmation (prompt-injection guard).

### Phase 3 — Agent loop
- New runtime loop: tool definitions + default order + dependency rules in the
  instructions; step limit; tool results appended; final streamed answer with a
  fixed reference set (the chat client requires references to be fixed before
  the first streamed text).
- Confirmation flow: `propose_tag_operation` and full-mode web addresses containing
  text you did not type pause the loop and
  ask the browser Yes/No (generalising today's `bulk_question` mechanism, which
  is session-bound and single-use); the loop resumes with the user's answer as
  the tool result.
- Status rows per tool call ("Looking up MetaList help · AI", "Reading 12 notes",
  "Opening 2 web pages", "Waiting for your confirmation").
- Graceful fallback for persistent bad tool calls.

### Phase 4 — Browser
- Yes/No confirmation card; new activity labels; accept new event types in the
  server and client allow-lists together.
- Remove client code serving the dead search path.

### Phase 5 — Remove the old routing
- Delete `ScopedRouteEnvelope`, route prompts, dispatch, the unused legacy
  `stream()`/`_run_steps` path and its global-index tools.
- Fix behaviours the survey found that the new design supersedes: chat-triggered
  accept/remove without confirmation; tag intent read from the last message only.

### Phase 6 — Live-LLM tests (evals)
- New eval stage `agent`: runs the **real** loop and tools against fixture notes,
  scopes and recorded web pages, through current production prompts.
- Expectations per case: which tools were used, in which order (default order
  plus allowed dependencies), whether a confirmation was requested (and that
  nothing changed without Yes), and a judged answer.
- Migrate the 63 route cases (37% of 170) to agent cases; keep the help-answer,
  web and summary stage cases that still apply; add cases for combinations the old
  design could not handle (help + web, notes + help, notes + web) and the reported
  release question.
- Matrix: each case on the supported models at Low, Medium and High thinking
  (Off kept where relevant). Before/after reports compared with
  `evals compare`; provider errors fail and stay in the denominator.
- Unit and browser tests updated alongside (runtime suite rewritten around the
  fake adapter).

### Phase 7 — Docs and help
- `docs/ui/ai-chat.md`, `docs/design/agent-harness.md`, `docs/AI-SUMMARY.md`,
  evals README, and the in-app help (`help-ai.md`, and the menus/help skills that
  describe routing).

## Answered questions

1. **Menus**: never ask before opening a dialog. Opening changes nothing, and
   destructive dialogs already require their own confirmation.
2. **Full web mode**: privacy is handled by the blacklist (blacklisted notes are
   never sent to the AI). Against prompt injection, addresses containing text you
   did not type yourself are shown in a Yes/No box before opening (option B).
3. **Release notes**: packaged from the README "Changes in" sections for the help
   tool.
4. **Live test budget**: the full matrix (models × Low/Medium/High × 5 trials) runs
   before merges; a smaller default set runs otherwise.
5. **Claude**: only the provider-neutral interface now, with the OpenAI
   implementation; no Claude adapter in this effort.

## Checkpoints

Commit checkpoint after each phase once tests (including live evals where
relevant) pass and you have tried it.
