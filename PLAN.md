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
- Done: `tool_calling.py` (tools, conversation shapes, validation, estimates),
  `InferenceAdapter.stream_tool_turn`, tool turns in history export. Live finding:
  OpenAI's Chat Completions rejects function tools combined with reasoning
  effort, so the OpenAI tool turn uses the **Responses API**; reasoning comes back
  as encrypted items and is handed to the next turn through an opaque
  `provider_state` on the assistant message (Claude's thinking blocks would use the
  same field). Live check: all 3 models × Off/Low/Medium/High call the tool and
  answer from its result.

### Phase 2 — Tools
- Implement the tools above on the frozen snapshot and privacy boundary, each
  with unit tests (budgets, privacy exclusion, invalid arguments, empty results).
- Release notes packaged for `lookup_metalist_help` (README "Changes in x.y.z"
  sections).
- Close web gaps found in the survey: re-check contextual-mode capability after
  redirects; in full mode, detect addresses containing text not typed by the user
  and require confirmation (prompt-injection guard).
- Done (read-only tools): `agent_tools.py` with `lookup_metalist_help`,
  `view_overview`, `search_view_notes`, `read_view_notes` and `open_web_pages`
  (offered only when web access is on), in the default order; bad arguments and
  unknown tools are explained back to the model instead of failing the run.
  `read_view_notes` takes note ids (any note selects its whole tree), reads in view
  order within the evidence budget and reports unread, too-large and unknown trees.
  Search matches every query word in text or tags, inside the frozen view only.
  New help topic `releases`, generated from the README by
  `scripts/sync_release_notes_help.py` and checked by a sync test; the help lookup
  also returns the installed version. Contextual web mode now checks every
  redirect hop. Live check: all 3 models accept every tool schema and, asked about
  0.11.0 and a note, call help then search, in the default order.
- Moved to Phase 3 (they need the loop's confirmation step): `open_menu`,
  `summarize_view`, `propose_tag_operation`, and the full-mode Yes/No for
  addresses containing text you did not type.

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
- Done: `agent_loop.py` (`AgentRuntime.stream_agent`), instructions in
  `prompts/agent.md`, interactive tools `open_menu`, `summarize_view`,
  `propose_tag_generation` and `propose_tag_review` (the planned
  `propose_tag_operation` is split in two, so no argument depends on another:
  generation is always the current view). Operations must be called alone and end
  the turn; their own confirmation runs (scope/focus card for generation and
  summaries, a new Yes/No `change_confirmation` with exact counts for accept/remove,
  which previously ran without asking). Full web mode asks Yes/No before opening an
  address with words the user did not type and that appeared in no known address.
  Limits: 8 model turns; two failed tool turns in a row, or the step limit, force a
  final answer; a silent ending gets one reminder. References may grow during a
  response but never shrink. Live check: 3 models at Low plus Luna at High,
  five requests each (help, notes, menu, tag review, chat), with correct tools and
  order (a silent Luna ending after a menu led to the reminder).
- Not yet wired to the chat route: that switch happens in Phase 4 together with
  the browser's Yes/No card.

### Phase 3b — AI instructions are no longer editable (your decision)
- Custom prompts would make it impossible to judge behavior against the evals, so
  prompts and skills (including the tagging instructions and help texts) are
  packaged only. Removed: the Agent prompts editor, `/api2/ai/prompts/defaults`,
  prompt/skill override resolution, and the instructions box in the tagging dialog,
  now "Tagging vocabulary" (`form.tagging_vocabulary`, vocabulary choice only).
- Saved overrides are retired preference keys: ignored on load and dropped on the
  next preference save. Help, docs and eval cases updated.

### Phase 4 — Browser
- Yes/No confirmation card; new activity labels; accept new event types in the
  server and client allow-lists together.
- Remove client code serving the dead search path.
- Done: the chat route runs `stream_agent` (with the tagging run); the old
  routing code is unreachable from the route and is deleted in Phase 5. Yes/No
  card (`confirmation-card.js`, pure `confirmation-question.js`) for
  `change_confirmation` questions, hosted in the chat's operation panel, not
  blocking the stream (Stop still ends the run); answers `yes`/`no` through
  `/proposals/answer`. New activity names allowed in the browser (`agent_turn`,
  tool names, `confirmation`, `tool_call_rejected`; a made-up tool name is never
  used as an activity name). Removed the dead `search_notes` activity label
  splitting and its styles. Help (`help-ai.md`) describes tools, the Yes/No
  confirmations and release notes. Browser check: the card shows the exact change,
  Yes posts the answer, the card closes and the turn completes.

### Phase 5 — Remove the old routing
- Delete `ScopedRouteEnvelope`, route prompts, dispatch, the unused legacy
  `stream()`/`_run_steps` path and its global-index tools.
- Fix behaviours the survey found that the new design supersedes: chat-triggered
  accept/remove without confirmation; tag intent read from the last message only.
- Done: deleted `actions.py`, `tools.py`, `permissions.py`, `markdown_validation.py`,
  the route/help/web/investigate runtime paths, dead context builders,
  `MetaListHelpResponse`, `TagOperationIntent`/`TaggingRun.stream`, the tool-result
  and help-response prompts and the scoped-investigation skill. `system.md` now
  serves whole-view summaries only. The selected-note size check moved into the
  agent loop. Summary tests now enter through `stream_agent`. Browser activity
  names trimmed to what the server still sends. Evals: only the summary stages
  remain; the 168 routing-era cases (including the reported release question) moved,
  unrun, to `evals/legacy-cases/` for Phase 6 migration; `from-export` removed with
  its route-only importer. Live check: "Summarize everything in this view" →
  `summarize_view` → confirmation → cited summary (Luna and Terra, Low).
- Your feedback: the full-mode Yes/No asked for ordinary Google searches and quotes.
  The rule now targets the actual risk, note text leaving in an address: ask only
  when an address contains words from notes shown to the AI that you did not type
  and that were not part of an address already seen (`NoteTextGuard`). Google Search
  and Google Finance are exempt; every redirect hop gets the same check. The box
  lists addresses separately (monospace, one per line) with compact buttons.
- Your feedback: a front-page story list had no links. The page result already
  carried a link token per story; Luna (Low) used them in only 2 of 6 runs. The
  agent instructions now carry the list-page rule the old final-response prompt had
  (each listed item cites its own link token; the page token only for the page as a
  whole). Live: 6 of 6 fully linked, links open the right stories. Luna also
  miscopied about 1 long id in 30, losing that link; fixed by giving the model short
  per-session tokens (`[[web:12]]`, numbered by the web evidence store) and
  translating them back to full evidence tokens as the answer streams
  (`web_citation_tokens.py`), so storage and rendering are unchanged. Live: 8 of 8
  runs (Luna ×6, Terra, Sol) linked all 30 stories correctly, none dropped.
- Left for Phase 7: design/UI/testing docs still describe the old routing
  (`docs/design/agent-harness.md`, `docs/ui/ai-chat.md`, `docs/testing/harness.md`,
  `docs/AI-SUMMARY.md`).

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
