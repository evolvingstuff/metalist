# Prompt regression suite

This is an explicitly invoked live suite, separate from pytest, browser smoke,
startup checks, and routine CI. Each selected case defaults to **10 times**;
`--repetitions 5` selects five fresh attempts for a shorter run. A case can
check structured actions, judge output quality, or check several decisions in
sequence. No replay executes application actions or reads the live note database.

The suite and its reviewed fixtures belong in Git. `evals/` and `tests/` are
excluded from both PyPI wheels and source distributions; the release artifact
check enforces that separation. Run this suite from a repository checkout.
The application's history recording and export button remain in the release.

## Synthetic action suite

[The 24-case action suite](cases/actions/README.md) uses only invented requests,
conversation history, and small view metadata. It originally covered three routes
equally. With help enabled, three explanation cases now expect `metalist_help`.
No personal notes, exports, paper corpus, or output judge are needed. Each case is
small including frozen prompts/schema.

[The 105-case help suite](cases/help/README.md) covers skill choice, menu selection,
permission/context cases and judged feature explanations. Its five-run measured
results are preserved separately from the older action suite.

```bash
# Validate all cases without making model calls.
.venv/bin/python -m evals run evals/cases/actions/*.json \
  --variant baseline --output /tmp/synthetic-actions-baseline

# Explicitly evaluate: 24 cases × 10 repetitions = 240 routing decisions.
.venv/bin/python -m evals run evals/cases/actions/*.json \
  --variant baseline --live --output /tmp/synthetic-actions-baseline
```

Instructor retries can add provider attempts. Use `--variant candidate` and a
different output directory after changing the main system prompt, then compare
reports with `python -m evals compare`. This suite measures action selection, not
the subsequent summary or application of proposals. See the case index for the
individual expectations and measured results.

## Capture a failure

In AI Chat, click **⇩ Export LLM history**. The downloaded JSON is a chronological
list of `[input, output]` pairs, one per provider attempt. Retries are separate
pairs. `input.request` is the actual HTTP JSON body sent to OpenAI (including
messages, response schema, and generation settings). `input.invocation` preserves
the application messages before Instructor adds schema/retry instructions.
`output` holds the raw response or streamed chunks, status, and error. Running,
cancelled, and failed calls remain distinguishable from completed responses.

History covers all turns since Clear Chat in the authenticated session. Reloading
the page retains it; Clear Chat, logout, and restarting the server remove it.
Exports contain the actual disclosed note content and conversation. No credential
headers are included. Review real content before committing it as a fixture.
Agent Debug still displays/copies the latest run, including application events.
Menu requests and browser results appear in `output.application_events` on the
producing call's pair. Requested and acknowledged opening are distinct events.

```bash
.venv/bin/python -m evals from-export /path/to/history.json \
  --pair 0 --output evals/cases/my-failure.json
```

Pair indices start at zero. The command creates an **unreviewed** draft; observed
output is retained as provenance, never copied into expected behavior. Edit the
description, expectations, and prompt bindings, then set `reviewed` to `true`.
The runner refuses unreviewed cases. For a failed retry, the draft reconstructs
the logical call from its original invocation, allowing Instructor to perform its
normal validation/retry path again. It does not replay only the retry request.

## Expected actions and output

For an action step, `expectation.alternatives` contains acceptable structured
results, for example `[{"kind": "respond"}]`. Dictionaries match specified fields;
omit free-form rationale wording unless relevant. Arrays match exactly in length
and order, so unexpected proposals/actions fail. Include target IDs, settings,
values, and scope when relevant. The production Instructor schema also validates
the structure of the result. It does not override intent using keyword rules.
A valid schema alone does not establish that an action is correct.

An output step instead lists criteria with stable IDs, instructions, and reference
facts. The judge must return exactly one reasoned verdict per criterion. All
criteria must pass for that repetition to count as correct. Each repetition
generates a fresh answer and judges that answer. The judge is also called through
Instructor. Its verdicts are saved for inspection; they are not infallible.

Each step has an explicit message list; it does not automatically inherit previous
steps. Include synthetic or recorded conversation/evidence directly. To include a
newly generated earlier output, use `{"role":"assistant","from_step":0}`.
There is no implicit accumulation of skill instructions. Step 5's skill only goes
into later calls if their message lists explicitly include it. Repetitions start
with fresh message lists and output history.

Starter cases cover asking about tagging, explicitly requesting proposals,
requesting a summary of saved notes, and a small judged summary example. They are
seed cases, not evidence of measured model accuracy.

## Baseline and revised prompts

`baseline` uses the literal captured messages in the case. `candidate` replaces
only explicitly bound instructions with the current contents of files. Paths are
relative to the case file. Files are read once per case before its repetitions.

`target: "skill"` reloads a skill Markdown file and takes exactly `skill_id` and
`trigger_action` variables to recreate its production wrapper. `json_instruction`
can replace the instruction in `FINAL_RESPONSE_REQUEST` or `METALIST_HELP_REQUEST`
while preserving the fixture context and catalog. Compare reports only when their
repetition counts and reviewed case inputs/expectations match.

```json
{
  "target": "message",
  "message_index": 0,
  "file": "../../app/services/agent/prompts/system.md",
  "variables": {}
}
```

Whole-message replacements target system/developer instructions. To change the
instruction inside a recorded `FINAL_RESPONSE_REQUEST`, use
`"target":"json_instruction"`, select that user-message index, and point to
`final-response.md`. Supply its captured `basis` in `variables`. Only that JSON
instruction changes; evidence, coverage, and conversation stay fixed. With no
template variables, file contents are literal, including any JSON braces.

Candidate runs require at least one explicit binding. Bind every prompt/skill
whose changes the test should measure. Unbound instructions remain frozen.
Cases preserve the response schema; a changed production schema requires explicit
case review instead of silently changing the baseline.

## Run and compare

Without `--live`, the command only validates cases and configuration. It makes no
provider calls and needs no API key. With `--live`, set `OPENAI_API_KEY` in the shell;
the runner does not read credentials from the user's MetaList namespace.

```bash
# Validate a case, then explicitly run its baseline ten times.
.venv/bin/python -m evals run evals/cases/tagging-question.json \
  --variant baseline --output /tmp/tagging-baseline
.venv/bin/python -m evals run evals/cases/tagging-question.json \
  --variant baseline --live --output /tmp/tagging-baseline

# After changing a bound prompt, evaluate the candidate ten times.
.venv/bin/python -m evals run evals/cases/tagging-question.json \
  --variant candidate --live --output /tmp/tagging-candidate
.venv/bin/python -m evals compare \
  /tmp/tagging-baseline/report.json /tmp/tagging-candidate/report.json

# Output judging requires explicit judge configuration.
.venv/bin/python -m evals run evals/cases/faithful-summary.json \
  --variant baseline --judge evals/judge.json --live --output /tmp/summary-baseline
```

Multiple case paths can be passed to `run`. Output directories must be new to
preserve previous results. Every completed repetition is written immediately, so
an interrupted batch retains completed results. Reports include the effective
case, fingerprints, judge configuration, each verdict/error, duration, and full
input/output pairs (including provider usage when supplied). Judge calls are
identified by `invocation.response_model: OutputJudgment`.

Example: **8 correct, 1 incorrect, 1 error → 8/10 (80%)**. Errors stay in the
denominator. Provider/validation retries are internal to a repetition; there is no
retry-until-pass policy. Comparisons require the same case/model/expectations and
judge, then show both percentages and the percentage-point change. Small samples
vary; 100% is not an acceptance requirement. No accuracy gate has been chosen.
Incorrect outputs do not cause a nonzero CLI status by themselves; any provider or
judge errors give exit status 2 after recording results. Invalid fixtures and
internal bugs fail loudly.

## Current boundary

These are decision/output replays using the production inference adapter and
schemas. They do not simulate a full interactive runtime, browser acknowledgments,
tag application, or state-dependent tool execution. Recorded earlier tool results
are fixtures; a multi-step case connects newly generated outputs only where
specified. Future settings/menu actions and their execution checks remain a
separate phase in PLAN.md. This runner makes it possible to establish prompt
regressions before adding those capabilities.

Infrastructure tests use a simulated HTTP provider with the real SDK/Instructor;
they exercise retries, partial/cancelled output, export isolation, prompt
substitution, skill lifetime, and ten-run aggregation without paid model calls.
Run the browser export check with `BROWSER_TEST_SUITE=ai-history npm run test:browser`.
