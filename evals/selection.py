"""Select changed current-production requests without replaying saved prompts."""

import json

from app.services.agent.judging import OutputJudgment
from evals.runner import fingerprint


def case_signature(case, prepared, judge, repetitions):
    uses_judge = any(step.expectation.kind == "output" for step in prepared.steps)
    if uses_judge:
        assert judge is not None
    return {"case_id": case.id, "case_fingerprint": fingerprint(case.model_dump()),
        "effective_fingerprint": fingerprint(prepared.model_dump()),
        "judge": judge.model_dump() if uses_judge else {},
        "judge_schema": OutputJudgment.model_json_schema() if uses_judge else {},
        "repetitions": repetitions}


def validate_coverage(entries):
    indexed = {}
    required = {"case_id", "case_fingerprint", "effective_fingerprint", "judge", "judge_schema",
                "repetitions", "counts", "source_report"}
    for entry in entries:
        if set(entry) != required or entry["case_id"] in indexed:
            raise ValueError("Invalid or duplicate baseline coverage entry")
        counts = entry["counts"]
        if (set(counts) != {"correct", "incorrect", "error"}
                or any(type(value) is not int or value < 0 for value in counts.values())
                or type(entry["repetitions"]) is not int or entry["repetitions"] < 1
                or sum(counts.values()) != entry["repetitions"]):
            raise ValueError("Incomplete baseline trial counts")
        if not entry["source_report"] or not entry["case_fingerprint"] or not entry["effective_fingerprint"]:
            raise ValueError("Baseline coverage requires provenance and fingerprints")
        indexed[entry["case_id"]] = entry
    return indexed


def recorded_judge_schema(case):
    """Read diagnostic schema metadata only; never replay captured instructions."""
    schemas = {}
    if "outcomes" in case:
        for outcome in case["outcomes"]:
            for request, _response in outcome["pairs"]:
                if "invocation" not in request:
                    continue
                invocation = request["invocation"]
                if invocation["response_model"] == "OutputJudgment":
                    schema = invocation["response_schema"]
                    if not schema:
                        raise ValueError("Recorded judge call has no response schema")
                    schemas[fingerprint(schema)] = schema
    if len(schemas) > 1:
        raise ValueError("Baseline contains inconsistent judge schemas")
    if not schemas:
        return {}
    return next(iter(schemas.values()))


def load_coverage(path):
    report = json.loads(path.read_text(encoding="utf-8"))
    if "coverage" in report:
        return validate_coverage(report["coverage"])
    entries = []
    for case in report["cases"]:
        if case["schema_version"] != 2 or case["prompt_source"] != "current-production":
            raise ValueError("Selective runs require current-production v2 reports")
        if fingerprint(case["effective_case"]) != case["effective_fingerprint"]:
            raise ValueError("Baseline effective request fingerprint does not match")
        uses_judge = any(step["expectation"]["kind"] == "output" for step in case["effective_case"]["steps"])
        # Older reports may retain the schema only in diagnostic call records.
        judge_schema = {}
        if uses_judge:
            judge_schema = recorded_judge_schema(case)
        entries.append({key: case[key] for key in
            ("case_id", "case_fingerprint", "effective_fingerprint", "repetitions", "counts")}
            | {"judge": case["judge"] if uses_judge else {}, "judge_schema": judge_schema,
               "source_report": str(path.resolve())})
    return validate_coverage(entries)


def plan_selection(cases, prepared_cases, *, judge, repetitions, baseline_path):
    baseline = {}
    mode, baseline_name, new_reason = "all", "", "full_run"
    if baseline_path is not None:
        baseline = load_coverage(baseline_path)
        mode, baseline_name, new_reason = "changed_since", str(baseline_path.resolve()), "new_case"
    selected, skipped = [], []
    for case, prepared in zip(cases, prepared_cases, strict=True):
        signature = case_signature(case, prepared, judge, repetitions)
        reason = new_reason
        if case.id in baseline:
            before = baseline[case.id]
            differences = [key for key in signature if signature[key] != before[key]]
            if not differences:
                skipped.append(case.id)
                continue
            reason = ",".join(differences)
        selected.append({"case_id": case.id, "reason": reason})
    plan = {"mode": mode, "baseline": baseline_name,
        "selected": selected, "skipped": skipped,
        "baseline_cases_not_requested": sorted(set(baseline) - {case.id for case in cases})}
    return plan, baseline


def build_coverage(cases, prepared_cases, *, reports, baseline, judge, repetitions, report_path):
    fresh = {report["case_id"]: report for report in reports}
    assert len(fresh) == len(reports), "Duplicate fresh case reports"
    assert set(fresh).issubset({case.id for case in cases}), "Unexpected fresh case report"
    entries = []
    for case, prepared in zip(cases, prepared_cases, strict=True):
        if case.id in fresh:
            entries.append(case_signature(case, prepared, judge, repetitions)
                | {"counts": fresh[case.id]["counts"], "source_report": str(report_path.resolve())})
        else:
            entries.append(baseline[case.id])
    validate_coverage(entries)
    return entries
