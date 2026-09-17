# MetaList agent history, behavior regressions, skills, and actions

Status: **Draft — awaiting user approval.**

Date: 2026-09-17.

This plan records the discussion and orders the work. It does not authorize
implementation before approval or settle the design questions listed below.

## Goals and agreed behavior

- Let the user export the complete LLM interaction history from a UI button:
  exactly what the model received at each step, what it returned, and what actions
  the application actually performed.
- Use recorded or synthetic contexts to construct initially failing behavior
  regressions before changing prompts to fix mistakes.
- Support two test types: action correctness and output quality. Use Instructor
  for structured model calls; use an LLM judge for output criteria that require
  semantic evaluation.
- Run live LLM regressions explicitly when prompts or skill instructions change.
  Ordinary tests, startup, and routine builds must not invoke models or judges.
- Run each live regression case 10 times and report its percentage correct.
  Correctness is measured as a rate; 100% is not assumed to be achievable or required.
- Extend the agent's knowledge of MetaList so it can explain features, open the
  appropriate menus/dialogs, and perform specifically supported operations.
- Preserve the current context as the boundary for note operations. Application
  help may describe all MetaList features without reading unrelated notes.
- Automatically opening a clearly relevant menu/dialog is acceptable. Opening a
  dialog alone does not authorize submitting it.
- Interpret the complete request and conversation. Do not impose a rule that
  “how do I…” requests can only receive explanations or open dialogs. For example,
  “how do I change the agent context to 250k tokens” can appropriately result in
  setting the relevant limit to 250,000.
- Work from concrete cases before designing a broad action or skill framework.

## Existing implementation to build on

- `app/api/routes/ai.py` verifies the active tab/search/sort context, freezes the
  permitted note scope, and invokes the scoped runtime.
- `app/services/agent/runtime.py` normally makes a routing call and then a final
  answer call for conversation/investigation. Tagging can make additional calls.
  Active routes are `respond`, `investigate_current_scope`, and `tag_proposals`.
  Older action definitions are not evidence that the current chat exposes them.
- `app/services/agent/skill_settings.py` registers one packaged investigation
  skill, selected by its action, with namespace-specific instruction overrides.
- `app/services/agent/context.py` constructs model-visible messages and injects
  activated skills. The agent currently receives no complete MetaList help guide.
- `app/services/agent/structured_inference.py` and `openai_inference.py` capture
  structured requests, provider request bodies, responses, and validation attempts.
- `app/services/agent/trace.py` retains only the latest run in session memory.
  Starting another run replaces it. Agent Debug's existing Copy all exports that
  run, not the internal call history of the whole conversation.
- `app/services/agent/tagging_run.py` records completed inference attempts, but
  failure paths need review. Final text response recording also needs to preserve
  partial output when a stream fails or is cancelled.
- `app/static/js/modules/command-palette/endpoint-registry.js` already identifies
  commands, settings, and dialog handlers. The chat stream currently has no general
  event for requesting and acknowledging those UI operations.
- Proposed tags are stored separately from accepted tags. Individual proposal
  controls and bulk operations have different undo behavior: successful bulk
  changes clear existing undo history and create no bulk undo entry. Do not
  assume all existing or future actions are undoable.

## Phase 1 — Complete interaction recording and UI export

- [ ] Define a versioned, structured export format with stable conversation, turn,
  run, call, attempt, and action identifiers and chronological event ordering.
- [ ] Retain every run belonging to the exportable conversation instead of only
  the latest run. Preserve each call's actual model-visible history, which may
  differ from the displayed transcript because of disclosure boundaries.
- [ ] Capture the exact effective inputs at call time:
  - System/developer instructions, prompt overrides, and loaded skill text.
  - Ordered messages and their roles, supplied note data, tool/action schemas,
    structured response schemas, and tool results available to that call.
  - Provider/model identity, relevant generation settings, application/export
    version, and prompt/skill versions or hashes.
  - The application context needed to interpret actions: current scope, relevant
    settings and UI state, available commands, and disclosed note snapshots.
- [ ] Record raw returned outputs and parsed structured values, validation errors,
  retry requests, failures, cancellations, and partial streamed outputs. Capture
  only data actually returned by the provider; do not claim access to hidden
  model reasoning.
- [ ] Record requested actions separately from actual execution and results,
  including relevant before/after state and failures. A model saying it opened a
  dialog is not proof that the browser opened it.
- [ ] Cover routing, investigation, tagging interpretation, all tagging batches,
  validation retries, and final response generation through the same export.
- [ ] Add a discoverable **Export LLM history** button to the chat UI, producing
  JSON suitable for constructing regression cases. Reuse Agent Debug where useful;
  exact button placement and whether Copy all remains are review decisions.
- [ ] Export the recorded snapshots without another model call. Do not rebuild
  past inputs from today's notes, preferences, or prompt files.
- [ ] Resolve retention and lifecycle before implementing storage: current-chat
  memory versus persistence across reload/restart, and behavior on Clear Chat,
  logout, cancellation, and concurrent export. An export taken during a running
  turn must identify that turn as incomplete.
- [ ] Preserve existing authentication, namespace isolation, and disclosure rules.
  Export model-visible content faithfully; omit credentials and authentication
  headers. Do not add undisclosed note data to make a case easier to reproduce.
  Choose retention/storage consistent with namespace encryption if persistence
  is selected. Never silently truncate a supposedly complete history.

Acceptance:

- A multi-turn interaction with routing, a skill, tagging batches, and retries can
  be exported with each request paired to its output or explicit failure state.
- Earlier calls survive later turns. A failed or cancelled turn remains inspectable.
- Changing notes/settings after a call does not change its exported context.
- Existing debug inspection, chat rendering, and cancellation continue working.
- Exporting performs no inference and does not mutate notes or settings.

## Phase 2 — Recorded and synthetic regression cases

- [ ] Define a case format that supports both adapted exports and entirely
  synthetic conversations, note data, application state, and action results.
- [ ] Preserve recorded behavior as evidence and separately specify expected
  behavior. A recorded mistake must not automatically become the expected answer.
- [ ] Keep original effective prompts and skills for baseline reproduction, while
  preserving enough input structure to rebuild requests with candidate prompts.
  Replaying unchanged serialized requests would not test a prompt modification.
- [ ] Allow cases targeting one particular decision/output or a complete sequence
  of decisions. Earlier messages, actions, and tool results remain available when
  they are needed to understand a follow-up.
- [ ] Reconstruct scope and relevant state from the case rather than querying live
  notes. If an action needs fixture data that is missing, fail explicitly instead
  of reading the user's workspace or inventing a result.
- [ ] Run execution checks against disposable state or controlled command handlers.
  Regressions must not change live preferences/notes, open the user's dialogs, or
  submit real application operations.
- [ ] Supply a documented workflow for turning an export into a case, adding its
  expectations, and running that case before editing prompts. Automatic generation
  of expected behavior is not assumed.

Acceptance: construct a synthetic case and a case derived from an exported failure;
both can be run independently of the original live conversation or database.

## Phase 3 — Action correctness regressions

- [ ] Invoke the real Instructor-backed decision path with the case context.
  Mock-only tests cannot establish that the live model selects the correct action.
- [ ] Compare structured actions and arguments with case-specific expectations:
  required actions, permitted alternatives, forbidden actions, intended targets,
  scope, values, and ordering where order affects correctness.
- [ ] Evaluate the action sequence overall. Do not require identical explanatory
  wording or an identical sequence when several sequences satisfy the case.
- [ ] Where execution is part of the case, check the resulting state or handler
  acknowledgment as well as the model's requested action.
- [ ] Treat Instructor schema validation as structural validation. A valid action
  object still fails if it targets the wrong setting, scope, or value.
- [ ] Report expected versus actual actions, missing/extra actions, and execution
  failures with links/identifiers back to the recorded calls.

Initial cases, with expected behavior reviewed before implementation:

| Request/context | Behavior to evaluate |
| --- | --- |
| Ask to summarize the current notes | Investigate the frozen permitted scope and preserve its boundary. |
| Ask a question about tagging | Answer the question without treating it as authorization to generate or accept proposals. |
| Explicitly request tag proposals | Enter the existing proposal workflow and preserve the separate proposal category. |
| “Where do I change the OpenAI model?” | Open the appropriate settings dialog; no model value has been specified. |
| “How do I change the agent context to 250k tokens?” | Setting the evidence/context limit to 250,000 is appropriate; distinguish it from the tagging batch limit. |
| Follow-up that depends on earlier conversation | Resolve the intended setting/action from that history. |

Cases for new capabilities may start out unsupported/failing. Keep that distinction
visible rather than presenting all planned examples as existing functionality.

## Phase 4 — Output quality regressions with an LLM judge

- [ ] Save explicit output criteria and supporting reference facts/evidence with
  each output case. Do not use exact prose matching as the quality test.
- [ ] Generate a fresh candidate output for each of the case's 10 repetitions,
  using the same starting context and selected prompts, and judge each output.
  Judging one fixed output 10 times does not satisfy this requirement.
- [ ] Use an Instructor-validated judge response with per-criterion verdicts,
  reasons, and an overall result. Select the judge prompt/model and pass rule
  explicitly, and record them with each run.
- [ ] Use ordinary assertions for objectively checkable facts such as valid
  citations, required structured values, and scope membership; use the judge for
  semantic criteria such as whether an explanation answers the question correctly.
- [ ] Keep candidate and judge calls identifiable in reports. Candidate text is
  material to evaluate, not authority for changing the judging criteria.
- [ ] Treat judge/provider failures as test errors, not passes. Preserve each
  repetition's verdict or error; do not retry until a test happens to pass.

Acceptance: an intentionally incorrect output fails its criteria, and an acceptable
paraphrase can pass without matching a reference answer word for word. Judge results
remain reviewable evidence rather than a guarantee of correctness.

## Phase 5 — Explicit execution and failing-test-first workflow

- [ ] Place live behavior cases behind a separate opt-in command/suite, with case
  selection and explicit model/judge configuration. Exact command names are TBD.
- [ ] Keep normal pytest, Node tests, browser smoke, startup checks, and routine CI
  free of live provider/judge calls. Test the regression infrastructure itself with
  deterministic fixtures in those ordinary suites.
- [ ] Run every selected action or output case exactly 10 times, resetting its
  conversation, fixture data, and application state before each repetition.
  Repetitions must not inherit actions or conversation from earlier repetitions.
- [ ] Report each case's correct count and percentage, for example **8/10 (80%)**,
  alongside incorrect and error counts and all individual outcomes. Keep errors
  visible in the denominator rather than dropping them to inflate the rate.
  Record ordinary inference retries within their repetition, not as new successes.
- [ ] Do not impose a universal 100% requirement. Overall acceptance thresholds
  and what constitutes a meaningful regression remain decisions for discussion;
  distinguish each repetition's verdict from the case's measured success rate.
- [ ] Intended workflow: export a failure → add expected behavior → establish a
  failing case → edit prompts/skills → rerun that case and the relevant behavior
  set → inspect changes and results.
- [ ] Report prompt/skill identities, model identities/settings, action/output
  verdicts, errors, call counts, latency, and provider usage/cost when available.
- [ ] Preserve the baseline and candidate results. Hold conversation, note data,
  expectations, and model settings fixed when measuring a prompt-only change.
  Run each case 10 times for the baseline and 10 times for the candidate, and
  report both percentages and their percentage-point difference. Exact provider
  reproducibility is not guaranteed by recording a context; these measured rates
  can vary between runs.
- [ ] Do not silently update expected results when a candidate prompt fails.

## Phase 6 — Concrete MetaList skills and actions

Begin this phase only after reviewing the specific initial behaviors and establishing
recording/regression support. Do not automatically expose every menu command.

- [ ] Start with the discussed AI-settings examples: explain the relevant controls,
  open AI Agent Settings, and set the context/evidence limit when the request calls
  for it. Review each behavior and its regression cases before broadening coverage.
- [ ] Reuse existing application commands and preference validation. Use explicit
  desired values instead of blindly toggling/cycling a UI control.
- [ ] Preserve current-context checks. Recheck relevant state before an action so
  a changed tab or edit cannot redirect a previously selected operation silently.
- [ ] Add browser execution acknowledgments where needed so recorded outcomes
  distinguish requested, completed, rejected, and failed UI operations.
- [ ] Evaluate what these specific cases need in the general prompt, compact action
  descriptions, or a looked-up skill. Do not prescribe a skill for every feature
  category before measuring instruction size, correctness, and latency.
- [ ] Keep actual command identifiers, allowed values, and validation owned by the
  application. Skill text explains their meaning and appropriate use.
- [ ] Record the effective skill text and its source/version on every activation;
  prompt/skill overrides must be reflected in exported history and replay.

Latency constraint:

A skill selected by the model in one call requires a later model call to use the
newly loaded instructions. Local file loading avoids network inference for loading
itself, but does not remove that second model round trip. A single-call action
decision requires the necessary instructions to be available before the call starts.
Compare concrete flows and their call counts; the existing two-call runtime is a
baseline, not a mandatory architecture or a free latency budget.

## Decisions still requiring discussion

1. Export retention: current conversation only, and what must survive reload,
   Clear Chat, logout, or application restart?
2. Export UX: button placement, download versus copy options, and whether selecting
   a particular turn should also be available alongside the complete history.
3. Case authoring: initially edit a structured case file, or also provide an explicit
   “add regression case” UI? Export is agreed; a full test-authoring UI is not.
4. Expected-action rules: permitted alternatives and degree of execution checking
   for the first concrete examples.
5. Output judging: rubric format, judge model/prompt, and per-output pass rule.
   Each case runs 10 times; acceptable overall rates and regression thresholds
   still need discussion and must not default to requiring 100%.
6. Initial skills/actions beyond AI settings, and which instructions justify lookup
   latency. No broad capability expansion is approved by this draft.

## Validation and documentation

- Add meaningful deterministic tests for trace ordering, multi-turn retention,
  exact snapshots, failures/retries/cancellation, export isolation, prompt
  substitution, expectation matching, judge-result validation, and 10-repetition
  aggregation with state reset and explicit error accounting.
- Exercise export through the real browser UI after successful and failed runs,
  including a multi-step conversation. Verify Chrome and Firefox where available;
  report actual platform/browser coverage without claiming untested coverage.
- Use synthetic data and disposable namespaces for automated execution checks.
- Document the export schema, live-suite invocation, case authoring, judge criteria,
  prompt-fix workflow, and actual limitations in `docs/testing/harness.md`,
  `docs/design/agent-harness.md`, `docs/ui/ai-chat.md`, and `docs/AI-SUMMARY.md`.
  Reconcile stale read-only descriptions in the UI docs with the already-existing
  tag proposal route and any newly approved actions.
- Follow `docs/testing/compatibility-gates.md`. No incidental changes to networking,
  CSP, startup, backup artifacts, recovery, or release gates.

## Approval and git workflow

- [ ] User reviews and approves this draft before implementation.
- [ ] After approval, request permission for the PLAN workflow's documentation-only
  **COMMIT CHECKPOINT** so the agreed plan is preserved.
- [ ] Confirm the implementation branch/base without merging or completing the
  unfinished Grammarly feature as a side effect. This draft was created on
  `feature/grammarly-editing`, whose prior checkpoint is `6275bf1b`.
- [ ] Implement and validate the approved phases, keeping this plan current.
- [ ] Follow the repository's testing/commit requirements. Remove `PLAN.md` only
  through the eventual **COMMIT FEATURE** workflow; never push automatically.
