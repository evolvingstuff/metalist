# Prompt regression suite

Regression runs always exercise **current production prompts and request builders**
against fixed scenarios and expected behavior. Cases contain conversation, scope,
selected-note data or evidence, and expectations. They contain no executable
captured system prompts, catalogs, response schemas, or prompt bindings.

`evals/production.py` calls the application's `AgentContextBuilder` with current
packaged prompts and skills. Routing instructions, help/menu catalogs, selected-note
context, final-response formatting, and response schemas therefore track production
changes automatically. The suite tests packaged defaults; it does not read a user's
namespace prompt overrides, credentials, or live note database.

Latest measured run: [September 19 results](RESULTS-2026-09-19.md): 757/760 correct;
three existing cases scored 4/5, with no provider errors. All 95 selected-note
trials passed, including 35 availability trials. Each case ran five times. A subsequent focused cached-title run passed 10/10;
all 152 earlier effective requests were verified unchanged.

## Run current prompts and compare reports

This live suite is opt-in, separate from pytest, browser tests, startup checks, and
routine CI. Cases default to five independent repetitions. Without `--live`, the
command builds and validates requests without provider calls or an API key.

Execution defaults to four concurrent requests (`--concurrency 4`); use
`--concurrency 1` for serial execution. All current production requests are prepared
before inference begins. Cases are grouped by model, reasoning setting, response
schema, and the leading system/developer messages. For each group, the first
successful request finishes before concurrent requests using that prefix proceed.
That first request is a scored trial, not an extra paid warm-up call. Each case's
five trials run sequentially, allowing later trials to reuse its full input prefix.
Judge calls share the same concurrency bound and prefix coordination. Histories,
outputs, errors, and report files remain isolated per case and repetition.

This scheduling encourages reuse without altering production messages or API
options. GPT-5.6-family models route caches automatically; no artificial cache keys,
retention changes, or prompt padding are added. Cache hits are not guaranteed:
prefix length, provider placement, and cache availability still matter. Reports
include actual cached, cache-write, and uncached input-token counts from the
provider, including judges and retries. See the
[official OpenAI caching guidance](https://developers.openai.com/api/docs/guides/prompt-caching).

```bash
# Validate all cases against current production code; no paid calls.
.venv/bin/python -m evals run evals/cases/*.json evals/cases/actions/*.json \
  evals/cases/help/*.json evals/cases/selected-note/*.json \
  evals/cases/web/*.json \
  --judge evals/judge.json --output /tmp/metalist-regressions-check

# Record current performance before editing production prompts.
.venv/bin/python -m evals run evals/cases/actions/*.json \
  --live --output /tmp/metalist-before

# After editing prompts/code, repeat the same cases and compare saved reports.
.venv/bin/python -m evals run evals/cases/actions/*.json \
  --live --output /tmp/metalist-after
.venv/bin/python -m evals compare \
  /tmp/metalist-before/report.json /tmp/metalist-after/report.json

# Output cases need an explicit judge; five repetitions is the default.
.venv/bin/python -m evals run evals/cases/selected-note/*.json \
  --judge evals/judge.json --repetitions 5 --live --output /tmp/metalist-selected
```

## Run only affected cases

For prompt or skill edits, pass the full candidate suite with
`--changed-since /path/to/previous/report.json`. The runner still builds every
request through current production code, but only changed or new cases make live
calls. No hand-maintained skill dependencies or frozen-prompt execution are used.

```bash
# Preview affected cases and why they were selected; no API calls.
.venv/bin/python -m evals run evals/cases/*.json evals/cases/actions/*.json \
  evals/cases/help/*.json evals/cases/selected-note/*.json \
  evals/cases/web/*.json \
  --judge evals/judge.json --changed-since /tmp/metalist-before/report.json \
  --output /tmp/metalist-affected-preview

# Add --live and use a new output directory to run that selection.
```

- A detailed skill edit selects cases that actually include that skill. Shared
  system instructions, catalogs, context builders, response schemas, scenario
  inputs, expectations, model settings, and repetition changes select every
  affected case automatically. A changed step reruns its entire multistep case.
- Judge configuration/schema changes select judged-output cases only. Older
  reports can use their recorded diagnostic judge schemas without replaying any
  prompts. If that provenance is absent, output cases are conservatively rerun
  once. Missing cases always run; malformed or incomplete baselines fail.
- Selected cases still default to five repetitions and four concurrent requests,
  with the same cache-aware scheduling. No changes means no provider calls and no
  API key is required, even with `--live`.
- `cases` contains only fresh results. `selection` identifies selected/skipped
  cases and reasons. `coverage` retains compact prior results with their original
  report paths, allowing the new partial report to be the next baseline without
  losing coverage. Skipped results are historical, never newly measured passes.
- Previously recorded failures/errors remain visible and preserve exit status 1/2
  until those cases are rerun successfully. They are not silently erased by a
  passing affected subset. `compare` labels results that were not rerun.

Omit `--changed-since` to force a full run. Do this when changing provider adapters,
execution/evaluation logic, or other behavior not represented in prepared requests;
request comparison cannot detect external model changes under the same model name.
This selection is an optimization for prompt regressions, not a substitute for
ordinary tests of note retrieval, privacy filtering, or the application runtime.

Live runs with selected cases require `OPENAI_API_KEY` in the shell. Reports must use new directories.
Every completed repetition is saved immediately. Reports retain actual generated
requests, current schemas, raw provider pairs, judge verdicts, errors, timings,
and estimated cost. Scenario and effective-request fingerprints are separate:
comparisons allow prompts to change but reject changed scenarios, expectations,
models, judges, or repetition counts. Keep before/after reports; there is no mode
that reruns frozen old prompts. Historical v1 reports are archival results and are
not comparable to migrated v2 fingerprints; establish a new v2 report for comparison.

**Exit status:** 0 means all repetitions passed; 1 means at least one incorrect
answer; 2 means at least one provider/judge error. Errors stay in the denominator:
8 correct, 1 incorrect, 1 error is 80%. Instructor retries are internal to a trial;
there is no retry-until-pass policy. Internal bugs and invalid fixtures fail loudly.
Small samples and LLM judges have uncertainty; inspect individual verdicts.

## Fixed expectations and scenarios

The [24 action cases](cases/actions/README.md) check initial route selection;
[105 help cases](cases/help/README.md) cover routing, menus, and explanations.
Starter cases and 21 selected-note cases cover additional requests and output quality,
including URL parents with child abstracts, sibling comparisons, ancestor context,
per-node tags, citations to the actual supporting node, and no-selection versus
selected-but-blocked explanations.
Two cached-title cases store raw HTML and fixed cached URL/title pairs; current
production text extraction formats that evidence on every run. These cases verify
identifying a selected abstract's title from its parent URL and citing that parent.
The v2 migration preserved all 133 original expectations. Historical measured
results remain historical; they do not establish current prompt accuracy.

Action `expectation.alternatives` entries match specified dictionary fields.
Arrays must match exactly in length/order; scalar types must match. Do not score
free-form reasons unless needed. Output cases specify stable criterion IDs,
instructions, and reference facts. Every criterion must pass; missing or duplicate
judge criteria count as errors. Do not revise expectations simply to pass a new prompt.

Each step has `conversation`, a tagged `context`, `max_output_tokens`, and
`expectation`. Supported contexts are `route`, `help`, `respond`, `investigation`,
`web_action`, and `web_respond`.
Scope metadata and selected-note state are explicit. Selection fixtures can provide
a complete containing tree with required node IDs, parent IDs, content, and tags;
production code derives the edited-node marker from the selected ID. Existing
single-node scenarios remain fixed and use the same current tree serializer.
Help contexts select topics;
current skills and catalogs are assembled by production code. Investigation
contexts supply fixed result trees and coverage IDs. A scenario never executes
application actions or retrieves actual notes.

Steps and repetitions are independent. To use a freshly generated earlier output,
include `{"role":"assistant","from_step":0}` in a later step's conversation.
Only these explicit references carry generated outputs forward. Skills and runtime
instructions are reconstructed for each step and never accumulate implicitly.

## Capture a failure

AI Chat's **⇩ Export LLM history** exports chronological `[input, output]` pairs,
one per provider attempt. `input.request` records the HTTP request;
`input.invocation` records application messages before Instructor's schema/retry
instructions. Output records responses, chunks, status, errors, and application
menu events. Exported note content is real: review it before committing fixtures.
No credential headers are included. History covers the authenticated session since
Clear Chat; logout/server restart also clear it.

```bash
.venv/bin/python -m evals from-export /path/to/history.json \
  --pair 0 --output evals/cases/my-failure.json
```

Indices are zero-based. Extraction produces an **unreviewed** scenario draft.
It strips generated instructions, retaining fixed conversation/scope/selection and
help-topic inputs. The original pair remains diagnostic provenance only. Expected
behavior must be written independently; observed output is never adopted as truth.
Review the extracted scenario, description, and expectations before setting
`reviewed: true`. Unsupported stages fail explicitly; investigation exports
currently require manual extraction of fixed evidence into an investigation context.

## Coverage boundary

These tests check individual model decisions/outputs using production request
builders, schemas, and inference transport. They do not execute a full interactive
agent, tag mutations, retrieval, or browser acknowledgments. Runtime and browser
tests cover those paths separately. A passing mocked harness test or dry run proves
wiring, **not live model behavior**.

`tests/unit/test_prompt_regressions.py` checks production-change propagation,
fixed expectations, output judging, repetition isolation, exports, comparisons,
and failure exit statuses without paid calls. `test_agent_history.py` checks the
real SDK/Instructor against a simulated provider. Browser history export can be
checked with `BROWSER_TEST_SUITE=ai-history npm run test:browser`.

The suite belongs in Git but is excluded from PyPI wheels/source distributions.
The history recording/export feature remains part of the installed application.
