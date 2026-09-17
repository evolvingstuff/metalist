"""Explicit CLI: python -m evals {from-export,run,compare}."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.services.agent.openai_cost_tracking import OpenAICostTracker
from app.services.agent.openai_inference import OpenAIInferenceAdapter, validate_openai_model
from evals.models import JudgeConfig, RegressionCase
from evals.runner import prepare_case, run_case


def write_new(path: Path, payload) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(payload, output, indent=2)
        output.write("\n")


def from_export(arguments):
    history = json.loads(arguments.history.read_text(encoding="utf-8"))
    pair = history[arguments.pair]
    request, response = pair
    if request["schema_version"] != 1:
        raise ValueError("Unsupported export version")
    invocation = request["invocation"]
    users = [message["content"] for message in invocation["messages"] if message["role"] == "user"]
    current_request = users[-1]
    if current_request.startswith("ROUTE_SELECTION_REQUEST\n"):
        current_request = json.loads(current_request.split("\n", 1)[1])["current_user_request"]
    # lint: allow-PY004 rationale="choose the editable case expectation shape by call kind"
    expectation = ({"kind": "action", "alternatives": [{"REPLACE_WITH_EXPECTED_FIELD": "EXPECTED_VALUE"}]}
                   if invocation["kind"] == "structured" else
                   {"kind": "output", "criteria": [{"id": "correct", "instruction": "REPLACE_WITH_EXPECTED_BEHAVIOR"}],
                    "reference_facts": ""})
    case = RegressionCase.model_validate({
        "schema_version": 1, "id": arguments.output.stem,
        "description": "Describe this failure and the intended behavior.",
        "reviewed": False, "model": invocation["model"],
        "thinking_level": invocation["thinking_level"],
        "steps": [{"kind": invocation["kind"], "messages": invocation["messages"],
                   "response_model": invocation["response_model"],
                   "response_schema": invocation["response_schema"],
                   "max_output_tokens": invocation["max_output_tokens"],
                   "current_user_request": current_request,
                   "prompt_bindings": [], "expectation": expectation}],
        "provenance": {"export_pair_index": arguments.pair, "recorded_pair": pair},
    })
    write_new(arguments.output, case.model_dump())
    print(f"Created {arguments.output}; set expectations and reviewed=true before running.")


async def run(arguments):
    cases = [RegressionCase.model_validate_json(path.read_text(encoding="utf-8")) for path in arguments.cases]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Case IDs must be unique")
    judge = None
    if arguments.judge is not None:
        judge = JudgeConfig.model_validate_json(arguments.judge.read_text(encoding="utf-8"))
    # Validate everything before spending tokens or creating a report directory.
    for path, case in zip(arguments.cases, cases):
        validate_openai_model(case.model)
        prepare_case(case, variant=arguments.variant, directory=path.parent)
        if any(step.expectation.kind == "output" for step in case.steps) and judge is None:
            raise ValueError("Output cases require --judge")
    if judge is not None:
        validate_openai_model(judge.model)
    if not arguments.live:
        print(f"Validated {len(cases)} cases; add --live to make provider calls (10 runs per case).")
        return
    api_key = os.environ["OPENAI_API_KEY"]
    costs = OpenAICostTracker()
    adapter = OpenAIInferenceAdapter(api_key=api_key, cost_tracker=costs)
    arguments.output.mkdir(parents=True, exist_ok=False)
    reports = []
    for index, (path, case) in enumerate(zip(arguments.cases, cases)):
        case_directory = arguments.output / str(index)
        case_directory.mkdir()
        def preserve(outcome):
            write_new(case_directory / f"{outcome['repetition']:02d}.json", outcome)
            print(f"{case.id} {outcome['repetition']}/10: {outcome['status']}", flush=True)
        report = await run_case(case, adapter=adapter, judge=judge,
            variant=arguments.variant, directory=path.parent, on_repetition=preserve)
        write_new(case_directory / "report.json", report)
        reports.append(report)
        print(f"{case.id}: {report['counts']['correct']}/10 ({report['percent_correct']:g}%) correct; "
              f"{report['counts']['error']} errors")
    write_new(arguments.output / "report.json", {"cases": reports,
        "estimated_cost_usd": str(costs.snapshot().estimated_cost_usd)})
    if any(report["counts"]["error"] for report in reports):
        raise SystemExit(2)


def compare(arguments):
    baseline = json.loads(arguments.baseline.read_text(encoding="utf-8"))["cases"]
    candidate = json.loads(arguments.candidate.read_text(encoding="utf-8"))["cases"]
    left = {report["case_id"]: report for report in baseline}
    right = {report["case_id"]: report for report in candidate}
    if left.keys() != right.keys():
        raise ValueError("Comparisons require identical case sets")
    for case_id, before in left.items():
        after = right[case_id]
        if before["case_fingerprint"] != after["case_fingerprint"] or before["judge"] != after["judge"]:
            raise ValueError(f"Case context, expectations, model, or judge changed: {case_id}")
        if before["repetitions"] != 10 or after["repetitions"] != 10:
            raise ValueError("Comparisons require 10 repetitions per case")
        difference = after["percent_correct"] - before["percent_correct"]
        print(f"{case_id}: {before['percent_correct']:g}% → {after['percent_correct']:g}% "
              f"({difference:+g} percentage points); errors "
              f"{before['counts']['error']} → {after['counts']['error']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("from-export")
    extract.add_argument("history", type=Path)
    extract.add_argument("--pair", type=int, required=True, help="Zero-based exported pair index")
    extract.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("cases", type=Path, nargs="+")
    execute.add_argument("--variant", choices=["baseline", "candidate"], required=True)
    execute.add_argument("--judge", type=Path)
    execute.add_argument("--live", action="store_true")
    execute.add_argument("--output", type=Path, required=True, help="New directory for reports")
    comparison = commands.add_parser("compare")
    comparison.add_argument("baseline", type=Path)
    comparison.add_argument("candidate", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "from-export":
        if arguments.pair < 0:
            parser.error("--pair must be nonnegative")
        from_export(arguments)
    elif arguments.command == "run":
        asyncio.run(run(arguments))
    else:
        compare(arguments)


if __name__ == "__main__":
    main()
