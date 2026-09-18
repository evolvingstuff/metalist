# MetaList help and menu cases

105 synthetic cases: 27 skill-routing decisions, 54 menu destinations, 11 context/
permission cases, and 13 judged explanations. No personal notes or exports.
All five-run measured results, including failures, are in [RESULTS.md](RESULTS.md).

```bash
# Validate fixtures; no provider calls.
.venv/bin/python -m evals run evals/cases/help/*.json --variant candidate \
  --judge evals/judge.json --repetitions 5 --output /tmp/metalist-help-check

# Opt-in paid calls: five fresh generations per case, plus judges for output cases.
.venv/bin/python -m evals run evals/cases/help/*.json --variant candidate \
  --judge evals/judge.json --repetitions 5 --live --output /tmp/metalist-help-live
```

Routing cases score `metalist_help` and selected `help_topics`. Menu cases score
`MetaListHelpResponse.menu_id`, including `none` for explanation-only, prohibited,
quoted, hypothetical, unsupported, or ambiguous requests. Operations such as
delete, backup creation and toggles are menu highlights, never automatic execution.
Context-limit examples distinguish evidence from the tagging batch window and
check that the answer does not claim a setting was changed.

Output cases use an Instructor-validated LLM judge for detailed feature knowledge:
search, inheritance, formatting, references, privacy, context, proposals and
backups. A judge verdict can be wrong; preserve and inspect its reason.

Six encryption regressions add the exact reported at-rest question, backup
snapshot/password history, plaintext structural metadata versus encrypted file
metadata, logs/memory/logout, passwordless storage, and the routing decision.
Their frozen baseline retains the incomplete privacy skill; candidate bindings
load the expanded skill. This preserves the failing baseline for future review.

Candidate bindings reload the system prompt, selected skill files and the help
response instruction. Skill bindings preserve the production ACTIVE_SKILL wrapper
and literal Markdown braces. Routing catalogs and menu catalogs are frozen in
fixture messages: when changing their contents, explicitly refresh/review those
JSON fields. Schema changes fail until fixtures are reviewed. Baselines always
retain literal instructions. Outputs and skill text never accumulate implicitly
across steps or repetitions.

The live cases test isolated model decisions, not full application execution.
`test_agent_help.py` exercises the real two-call runtime, Instructor/SDK transport,
history and session-bound acknowledgments. `agent_menu_actions.test.mjs` tests
scope, cancellation, visibility and no execution of highlighted commands.
`BROWSER_TEST_SUITE=agent-help npm run test:browser` checks all 54 destinations,
late modal responses, and chat request/acknowledgment in a disposable namespace
with a simulated chat stream. Ordinary tests make no live LLM calls.
