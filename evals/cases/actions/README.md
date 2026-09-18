# Synthetic action-selection cases

All requests, conversations, and view metadata are invented. These cases use
no note contents and do not derive fixtures from personal exports. They test
the first routing decision only; no final answer, judge, or mutation is invoked.

Each case accepts exactly one route. The explanatory reason is not scored.
The table below defines expectations; measured results are recorded separately.

The initial live Luna run exposed a code defect: a keyword-based validator
rejected `respond` for “do not inspect current notes”. That validator, its prompt
signal, and a legacy rationale-text routing override have been removed. The
fixtures now omit the signal and its instructions; conversations, scope metadata,
and expected actions were unchanged at that checkpoint. Product help now adds a fourth route, so the three explanation cases below expect metalist_help. Instructor validates action structure, while
these tests score the model's choice. The original run remains a historical
application-level baseline (218/240 correct, 15 incorrect, 7 validation errors).

| Case | Expected action | Why |
| --- | --- | --- |
| [hello](hello.json) | `respond` | A greeting needs no saved-note evidence. |
| [general-knowledge](general-knowledge.json) | `respond` | A keyword matching the view does not by itself require investigation. |
| [tagging-help](tagging-help.json) | `metalist_help` | Asking how proposals work is not permission to generate them. |
| [hypothetical-accept](hypothetical-accept.json) | `metalist_help` | A hypothetical acceptance question must not mutate proposals. |
| [quoted-command](quoted-command.json) | `metalist_help` | An imperative inside quoted text is material to explain, not execute. |
| [acknowledge-correction](acknowledge-correction.json) | `respond` | A correction asking for acknowledgment does not require fresh evidence. |
| [rewrite-conversation](rewrite-conversation.json) | `respond` | Rewriting an answer already present in history needs no investigation. |
| [past-operation-count](past-operation-count.json) | `respond` | A count cannot establish which tags were changed; no new operation is authorized. |
| [summarize-notes](summarize-notes.json) | `investigate_current_scope` | An explicit summary of saved notes needs the frozen scope. |
| [papers-without-notes-word](papers-without-notes-word.json) | `investigate_current_scope` | A request about papers in the active view still depends on saved evidence. |
| [compare-saved](compare-saved.json) | `investigate_current_scope` | Comparison of two saved plans requires their current contents. |
| [empty-scope](empty-scope.json) | `investigate_current_scope` | Empty results do not turn a saved-note task into a general-knowledge task. |
| [changed-scope-retry](changed-scope-retry.json) | `investigate_current_scope` | A newly selected view overrides an earlier claim that evidence was missing. |
| [elliptical-continuation](elliptical-continuation.json) | `investigate_current_scope` | A short follow-up continues an unresolved saved-note task. |
| [inspect-current-proposals](inspect-current-proposals.json) | `investigate_current_scope` | Looking at proposals is evidence retrieval, not generating or accepting them. |
| [refresh-saved-answer](refresh-saved-answer.json) | `investigate_current_scope` | An explicit fresh check must investigate rather than reuse an old answer. |
| [generate-current](generate-current.json) | `tag_proposals` | Direct generation request selects the proposal workflow. |
| [generate-topic](generate-topic.json) | `tag_proposals` | A topic restriction still routes to proposal generation. |
| [accept-current](accept-current.json) | `tag_proposals` | Explicit bulk acceptance selects the proposal workflow. |
| [remove-current](remove-current.json) | `tag_proposals` | Explicit bulk removal selects the proposal workflow. |
| [reject-current](reject-current.json) | `tag_proposals` | Reject is an explicit proposal-removal request. |
| [accept-filtered](accept-filtered.json) | `tag_proposals` | Acceptance of a named proposed tag is a proposal operation. |
| [remove-filtered](remove-filtered.json) | `tag_proposals` | Removal of a named proposed tag is a proposal operation. |
| [help-then-explicit-action](help-then-explicit-action.json) | `tag_proposals` | A new explicit operation supersedes the previous help question. |

The three `tag_proposals` suboperations (generate/accept/remove), scope, and tag
filter are selected by a later inference call and are not asserted by this
routing-only suite. We can add separate synthetic cases for that decision.

Baseline uses the frozen instructions in each case. Candidate replaces the
main system prompt from its production file. The inline routing instruction
and response schema remain frozen; changes to those require explicit fixture
review. No current case expects unimplemented settings/menu actions.

Live verification after removing intent heuristics (2026-09-17): all 24 cases
passed 10/10 using gpt-5.6-luna, thinking off, with zero validation errors. Both
the removal-only and final system-prompt runs scored 240/240. The frozen prompts
now match the final evaluated version. These sample results do not guarantee
future perfect accuracy. See `docs/testing/harness.md` for report locations.

The five-run help-enabled results are in [help/RESULTS.md](../help/RESULTS.md). They preserve topic-expectation failures separately from schema validation errors.
