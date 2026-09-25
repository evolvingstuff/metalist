import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent.judging import OutputJudgment
from evals import __main__ as cli
from evals import production
from evals.models import JudgeConfig, RegressionCase
from evals.runner import prepare_case
from evals.selection import build_coverage, case_signature, load_coverage, plan_selection


ROOT = Path(__file__).resolve().parents[2]
JUDGE = JudgeConfig.model_validate_json((ROOT / "evals/judge.json").read_text())


def cases():
    return [RegressionCase.model_validate_json(p.read_text()) for p in sorted((ROOT / "evals/cases").rglob("*.json"))]


def save_baseline(path, scenarios):
    prepared = [prepare_case(case) for case in scenarios]
    reports = [{"case_id": case.id, "counts": {"correct": 5, "incorrect": 0, "error": 0}} for case in scenarios]
    coverage = build_coverage(scenarios, prepared, reports=reports, baseline={}, judge=JUDGE,
        repetitions=5, report_path=path)
    path.write_text(json.dumps({"cases": reports, "coverage": coverage}))
    return prepared


def selection(scenarios, baseline):
    return plan_selection(scenarios, [prepare_case(case) for case in scenarios],
        judge=JUDGE, repetitions=5, baseline_path=baseline)[0]


def test_skill_edit_selects_only_cases_that_actually_load_that_skill(tmp_path, monkeypatch):
    scenarios = cases()
    baseline = tmp_path / "before.json"
    save_baseline(baseline, scenarios)
    loader = production.load_skill
    monkeypatch.setattr(production, "load_skill", lambda name:
        loader(name) + "\nChanged AI skill guidance." if name == "help-ai.md" else loader(name))
    plan = selection(scenarios, baseline)
    expected = {case.id for case in scenarios if any(step.context.stage == "help"
        and "ai" in step.context.topics for step in case.steps)}
    assert expected and len(expected) < len(scenarios)
    assert {entry["case_id"] for entry in plan["selected"]} == expected
    assert all(entry["reason"] == "effective_fingerprint" for entry in plan["selected"])


def test_web_skill_edit_selects_only_web_skill_cases(tmp_path, monkeypatch):
    scenarios = cases()
    baseline = tmp_path / "before.json"
    save_baseline(baseline, scenarios)
    loader = production.load_skill
    monkeypatch.setattr(
        production,
        "load_skill",
        lambda name: (
            loader(name) + "\nChanged browsing guidance."
            if name == "web-browsing.md"
            else loader(name)
        ),
    )
    plan = selection(scenarios, baseline)
    expected = {
        case.id
        for case in scenarios
        if any(
            step.context.stage in {"web_action", "web_respond"}
            for step in case.steps
        )
    }
    assert expected and len(expected) < len(scenarios)
    assert {entry["case_id"] for entry in plan["selected"]} == expected


def test_system_prompt_edit_selects_every_existing_case(tmp_path, monkeypatch):
    scenarios = cases()
    baseline = tmp_path / "before.json"
    save_baseline(baseline, scenarios)
    loader = production.load_prompt
    monkeypatch.setattr(production, "load_prompt", lambda name:
        loader(name) + "\nChanged shared instructions." if name == "system.md" else loader(name))
    assert len(selection(scenarios, baseline)["selected"]) == len(scenarios)


def test_schema_change_selects_only_applicable_cases(tmp_path, monkeypatch):
    scenarios = cases()
    baseline = tmp_path / "before.json"
    save_baseline(baseline, scenarios)
    model = production.RESPONSE_MODELS["ScopedRouteEnvelope"]
    schema = model.model_json_schema() | {"description": "Changed route schema"}
    monkeypatch.setattr(model, "model_json_schema", classmethod(lambda cls: schema))
    expected = {case.id for case in scenarios if any(step.context.stage == "route" for step in case.steps)}
    assert {entry["case_id"] for entry in selection(scenarios, baseline)["selected"]} == expected


@pytest.mark.parametrize("change", ["config", "schema"])
def test_judge_changes_select_only_judged_cases(tmp_path, monkeypatch, change):
    scenarios = cases()
    baseline = tmp_path / "before.json"
    prepared = save_baseline(baseline, scenarios)
    judge = JUDGE
    if change == "config":
        judge = JUDGE.model_copy(update={"prompt": JUDGE.prompt + " Changed judge."})
    else:
        schema = OutputJudgment.model_json_schema() | {"description": "Changed judgment schema"}
        monkeypatch.setattr(OutputJudgment, "model_json_schema", classmethod(lambda cls: schema))
    plan, _ = plan_selection(scenarios, prepared, judge=judge, repetitions=5, baseline_path=baseline)
    expected = {case.id for case in scenarios if any(step.expectation.kind == "output" for step in case.steps)}
    assert {entry["case_id"] for entry in plan["selected"]} == expected


def test_new_case_and_changed_repetitions_are_never_skipped(tmp_path):
    scenarios = cases()[:2]
    baseline = tmp_path / "before.json"
    save_baseline(baseline, scenarios[:1])
    plan = selection(scenarios, baseline)
    assert plan["selected"] == [{"case_id": scenarios[1].id, "reason": "new_case"}]
    plan, _ = plan_selection(scenarios, [prepare_case(case) for case in scenarios],
        judge=JUDGE, repetitions=3, baseline_path=baseline)
    assert len(plan["selected"]) == 2


def test_partial_run_retains_unchanged_coverage_and_provenance(tmp_path):
    scenarios = cases()[:2]
    baseline = tmp_path / "before.json"
    save_baseline(baseline, scenarios)
    changed = scenarios[0].model_copy(update={"description": "Intentional scenario metadata change"})
    current = [changed, scenarios[1]]
    prepared = [prepare_case(case) for case in current]
    plan, before = plan_selection(current, prepared, judge=JUDGE, repetitions=5, baseline_path=baseline)
    assert plan["selected"][0]["reason"] == "case_fingerprint"
    after_path = tmp_path / "after.json"
    reports = [{"case_id": changed.id, "counts": {"correct": 5, "incorrect": 0, "error": 0}}]
    coverage = build_coverage(current, prepared, reports=reports, baseline=before, judge=JUDGE,
        repetitions=5, report_path=after_path)
    after_path.write_text(json.dumps({"cases": reports, "coverage": coverage}))
    assert coverage[0]["source_report"] == str(after_path.resolve())
    assert coverage[1]["source_report"] == str(baseline.resolve())
    assert selection(current, after_path)["selected"] == []


@pytest.mark.parametrize("status,exit_code", [("correct", 0), ("incorrect", 1), ("error", 2)])
def test_no_change_makes_no_calls_and_keeps_historical_failures(tmp_path, monkeypatch, status, exit_code):
    path = ROOT / "evals/cases/actions/hello.json"
    scenario = RegressionCase.model_validate_json(path.read_text())
    baseline = tmp_path / "before.json"
    save_baseline(baseline, [scenario])
    prior = json.loads(baseline.read_text())
    prior["coverage"][0]["counts"] = {key: 5 if key == status else 0 for key in ("correct", "incorrect", "error")}
    baseline.write_text(json.dumps(prior))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "OpenAIInferenceAdapter", lambda **kwargs: pytest.fail("No provider calls needed"))
    args = SimpleNamespace(cases=[path], repetitions=5, concurrency=4, judge=None,
        changed_since=baseline, live=True, output=tmp_path / "after")
    if exit_code:
        with pytest.raises(SystemExit) as error:
            asyncio.run(cli.run(args))
        assert error.value.code == exit_code
    else:
        asyncio.run(cli.run(args))
    report = json.loads((args.output / "report.json").read_text())
    assert report["cases"] == []
    assert report["selection"]["skipped"] == [scenario.id]
    assert report["coverage"][0]["counts"][status] == 5


def test_incomplete_baseline_cannot_silently_skip_trials(tmp_path):
    baseline = tmp_path / "before.json"
    save_baseline(baseline, cases()[:1])
    report = json.loads(baseline.read_text())
    report["coverage"][0]["counts"]["correct"] = 4
    baseline.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Incomplete"):
        load_coverage(baseline)


def test_cli_runs_only_changed_cases_and_carries_forward_the_rest(tmp_path, monkeypatch):
    scenarios = cases()[:2]
    baseline = tmp_path / "before.json"
    save_baseline(baseline, scenarios)
    changed = scenarios[0].model_dump()
    changed["steps"][0]["conversation"][-1]["content"] = "A revised user request"
    scenarios[0] = RegressionCase.model_validate(changed)
    paths = []
    for index, case in enumerate(scenarios):
        path = tmp_path / f"case-{index}.json"
        path.write_text(case.model_dump_json())
        paths.append(path)
    async def execute(selected, **kwargs):
        assert [case.id for case in selected] == [scenarios[0].id]
        assert "A revised user request" in str(kwargs["prepared_cases"][0].model_dump())
        assert kwargs["repetitions"] == 5 and kwargs["concurrency"] == 4
        return [{"case_id": selected[0].id, "counts": {"correct": 5, "incorrect": 0, "error": 0}}]
    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    monkeypatch.setattr(cli, "OpenAIInferenceAdapter", lambda **kwargs: object())
    monkeypatch.setattr(cli, "run_cases", execute)
    args = SimpleNamespace(cases=paths, repetitions=5, concurrency=4, judge=None,
        changed_since=baseline, live=True, output=tmp_path / "after")
    asyncio.run(cli.run(args))
    report = json.loads((args.output / "report.json").read_text())
    assert len(report["cases"]) == 1 and len(report["coverage"]) == 2
    assert report["coverage"][1]["source_report"] == str(baseline.resolve())


def test_legacy_report_rechecks_unknown_judge_schema_and_rejects_corrupt_fingerprint(tmp_path):
    scenarios = [RegressionCase.model_validate_json((ROOT / path).read_text()) for path in
        ("evals/cases/actions/hello.json", "evals/cases/faithful-summary.json")]
    reports = []
    for case in scenarios:
        prepared = prepare_case(case)
        record = case_signature(case, prepared, JUDGE, 5)
        del record["judge_schema"]
        reports.append(record | {"schema_version": 2, "prompt_source": "current-production",
            "effective_case": prepared.model_dump(), "counts": {"correct": 5, "incorrect": 0, "error": 0}})
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"cases": reports}))
    assert selection(scenarios, path)["selected"] == [{"case_id": scenarios[1].id, "reason": "judge_schema"}]
    reports[1]["outcomes"] = [{"pairs": [[{"invocation": {"response_model": "OutputJudgment",
        "response_schema": OutputJudgment.model_json_schema()}}, {}]]}]
    path.write_text(json.dumps({"cases": reports}))
    assert selection(scenarios, path)["selected"] == []
    reports[0]["effective_fingerprint"] = "corrupt"
    path.write_text(json.dumps({"cases": reports}))
    with pytest.raises(ValueError, match="fingerprint"):
        load_coverage(path)


def test_compare_labels_skipped_results_as_historical(tmp_path, capsys):
    scenarios = cases()[:1]
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    save_baseline(before, scenarios)
    after.write_text(json.dumps({"cases": [], "coverage": list(load_coverage(before).values())}))
    cli.compare(SimpleNamespace(baseline=before, candidate=after))
    assert "Not rerun; historical result" in capsys.readouterr().out
