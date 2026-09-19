import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent.inference import InferenceProviderError
from app.services.agent.judging import OutputJudgment
from evals.models import JudgeConfig, RegressionCase
from evals.runner import matches, prepare_case, run_case
from evals.__main__ import compare, from_export
from evals import production
from evals import __main__ as cli
from app.services.agent import context as production_context
from evals.runner import fingerprint
from evals.scenarios import scenario_from_invocation


ROOT = Path(__file__).resolve().parents[2]


def test_every_case_uses_changed_production_system_prompt(monkeypatch):
    original_loader = production.load_prompt
    monkeypatch.setattr(production, "load_prompt", lambda name:
        "Changed production system instructions" if name == "system.md" else original_loader(name))
    paths = list((ROOT / "evals/cases").rglob("*.json"))
    assert len(paths) >= 133
    for path in paths:
        scenario = RegressionCase.model_validate_json(path.read_text())
        before = scenario.model_dump()
        prepared = prepare_case(scenario)
        assert all(step.messages[0].content == "Changed production system instructions" for step in prepared.steps)
        assert scenario.model_dump() == before


def test_route_builder_changes_reach_existing_cases(monkeypatch):
    original = production_context.AgentContextBuilder.build_scoped_route_messages
    def changed(self, **kwargs):
        return original(self, **kwargs) + [{"role": "user", "content": "New runtime context"}]
    monkeypatch.setattr(production_context.AgentContextBuilder, "build_scoped_route_messages", changed)
    prepared = prepare_case(case("actions/hello"))
    assert prepared.steps[0].messages[-1].content == "New runtime context"
    assert any(m.content.startswith("SELECTED_NOTE_CONTEXT\n") for m in prepared.steps[0].messages)


def test_help_uses_current_skill_catalog_and_instruction(monkeypatch):
    monkeypatch.setattr(production, "load_skill", lambda name: "Changed skill with literal {braces}.")
    monkeypatch.setattr(production_context, "HELP_RESPONSE_INSTRUCTION", "Current help instructions")
    monkeypatch.setattr(production_context, "MENU_ACTIONS", [
        {"id": "new.menu", "label": "New menu", "presentation": "dialog"}])
    messages = prepare_case(case("help/context-value")).steps[0].messages
    assert any(m.content == "ACTIVE_SKILL help_ai_v1\nTrigger action: help_ai\n\nChanged skill with literal {braces}." for m in messages)
    payload = json.loads(messages[-1].content.split("\n", 1)[1])
    assert payload["instruction"] == "Current help instructions"
    assert payload["available_menus"] == [{"id": "new.menu", "label": "New menu", "presentation": "dialog"}]


def test_schema_changes_flow_into_requests_without_revising_scenarios(monkeypatch):
    model = production.RESPONSE_MODELS["ScopedRouteEnvelope"]
    schema = model.model_json_schema()
    schema["description"] = "Current schema changed"
    monkeypatch.setattr(model, "model_json_schema", classmethod(lambda cls: schema))
    source = case("actions/hello")
    before = source.model_dump()
    assert prepare_case(source).steps[0].response_schema == schema
    assert source.model_dump() == before


def test_current_final_prompt_changes_effective_fingerprint_only(monkeypatch):
    source = case("faithful-summary")
    before = prepare_case(source).model_dump()
    scenario_fingerprint = fingerprint(source.model_dump())
    original_loader = production.load_prompt
    monkeypatch.setattr(production, "load_prompt", lambda name:
        "Changed final instructions: {basis}" if name == "final-response.md" else original_loader(name))
    after = prepare_case(source).model_dump()
    assert fingerprint(before) != fingerprint(after)
    assert fingerprint(source.model_dump()) == scenario_fingerprint
    assert before["steps"][0]["expectation"] == after["steps"][0]["expectation"]
    assert before["steps"][0]["messages"][1] == after["steps"][0]["messages"][1]


def test_captured_prompts_and_schemas_are_not_allowed_in_scenarios():
    fixture = case("actions/hello").model_dump()
    fixture["steps"][0]["prompt_bindings"] = []
    with pytest.raises(ValueError, match="Extra inputs"):
        RegressionCase.model_validate(fixture)
    fixture = case("actions/hello").model_dump()
    fixture["steps"][0]["conversation"].insert(0, {"role": "system", "content": "Frozen instructions"})
    with pytest.raises(ValueError):
        RegressionCase.model_validate(fixture)


def test_selected_note_final_request_uses_current_evidence_and_catalog():
    scenario = case("selected-note/selected-summary")
    prepared = prepare_case(scenario)
    messages = prepared.steps[0].messages
    selected = next(m for m in messages if m.content.startswith("SELECTED_NOTE_CONTEXT\n"))
    payload = json.loads(selected.content.split("\n", 1)[1])["selected_note"]
    assert payload["note_id"] == "orchard-note"
    assert payload["tree_notes"] == [{"note_id": "orchard-note", "parent_id": "",
        "content_text": scenario.steps[0].context.selected_note.content_text, "tags": "garden", "is_selected": True}]
    final = json.loads(messages[-1].content.split("\n", 1)[1])
    assert final["response_mode"] == "direct_with_selected_note_evidence"
    assert "orchard-note" in json.dumps(final["reference_catalog"])


def test_cached_title_case_uses_current_production_extraction(monkeypatch):
    scenario = case("selected-note/cached-title")
    original = scenario.model_dump()
    prepared = prepare_case(scenario)
    assert "Do Transformers Need Three Projections?" in str(prepared.model_dump())
    extract = production.extract_agent_note_text
    def changed(**kwargs):
        content, redacted = extract(**kwargs)
        return content + " UPDATED_PRODUCTION_TITLE_FORMAT", redacted
    monkeypatch.setattr(production, "extract_agent_note_text", changed)
    assert "UPDATED_PRODUCTION_TITLE_FORMAT" in str(prepare_case(scenario).model_dump())
    assert scenario.model_dump() == original


def test_investigation_uses_current_builder_and_fixed_evidence():
    fixture = case("faithful-summary").model_dump()
    context = fixture["steps"][0]["context"]
    context.update(stage="investigation", result_trees=[], evidence_note_ids=[], result_tree_ids=[])
    prepared = prepare_case(RegressionCase.model_validate(fixture))
    payload = json.loads(prepared.steps[0].messages[-1].content.split("\n", 1)[1])
    assert payload["authoritative_result_trees"] == []
    assert payload["frozen_scope"]["note_count"] == 0


@pytest.mark.parametrize("name", ["tree-url-route", "tree-url-summary", "access-blacklisted", "access-none"])
def test_selected_tree_export_retains_scenario_and_rebuilds_selection(name):
    scenario = case(f"selected-note/{name}")
    prepared = prepare_case(scenario).steps[0]
    extracted = scenario_from_invocation(prepared.model_dump(), scenario.steps[0].expectation.model_dump())
    assert extracted.context.selected_note == scenario.steps[0].context.selected_note
    assert extracted.conversation == scenario.steps[0].conversation
    if name == "tree-url-summary":
        final = json.loads(prepared.messages[-1].content.split("\n", 1)[1])
        for node in scenario.steps[0].context.selected_note.tree_notes:
            assert node.note_id in json.dumps(final["reference_catalog"])


@pytest.mark.parametrize("invalid", ["missing_selection", "missing_parent", "duplicate", "cycle"])
def test_selected_tree_rejects_invalid_structure_before_live_requests(invalid):
    fixture = case("selected-note/tree-url-summary").model_dump()
    selected = fixture["steps"][0]["context"]["selected_note"]
    if invalid == "missing_selection":
        selected["note_id"] = "missing"
    elif invalid == "missing_parent":
        selected["tree_notes"][1]["parent_id"] = "missing"
    elif invalid == "duplicate":
        selected["tree_notes"].append(selected["tree_notes"][1].copy())
    else:
        selected["tree_notes"][0]["parent_id"] = selected["tree_notes"][-1]["note_id"]
    with pytest.raises(AssertionError):
        prepare_case(RegressionCase.model_validate(fixture))


def test_steps_and_repetitions_do_not_inherit_skills_or_outputs():
    fixture = case("help/context-value").model_dump()
    fixture["steps"][0]["expectation"] = {"kind": "action", "alternatives": [{"test": "ok"}]}
    next_step = case("actions/hello").steps[0].model_dump()
    next_step["conversation"].insert(0, {"role": "assistant", "from_step": 0})
    next_step["expectation"] = {"kind": "action", "alternatives": [{"test": "ok"}]}
    fixture["steps"].append(next_step)
    seen = []
    class Adapter:
        async def infer_structured(self, **kwargs):
            seen.append(kwargs["messages"])
            return SimpleNamespace(content=json.dumps({"test": "ok", "trial": len(seen)}))
    asyncio.run(run_case(RegressionCase.model_validate(fixture), adapter=Adapter(), judge=None,
        on_repetition=lambda outcome: None, repetitions=2))
    assert all("ACTIVE_SKILL" in json.dumps(m) for m in seen[::2])
    assert all("ACTIVE_SKILL" not in json.dumps(m) for m in seen[1::2])
    for index in (1, 3):
        prior = [m for m in seen[index] if m["role"] == "assistant"]
        assert prior == [{"role": "assistant", "content": json.dumps({"test": "ok", "trial": index})}]


@pytest.mark.parametrize("status,exit_code", [("incorrect", 1), ("error", 2)])
def test_cli_fails_for_wrong_behavior_and_provider_errors(tmp_path, monkeypatch, status, exit_code):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setattr(cli, "OpenAIInferenceAdapter", lambda **kwargs: object())
    async def fake_run(*args, **kwargs):
        return [{"case_id": args[0][0].id, "counts": {"correct": 0, "incorrect": int(status == "incorrect"),
                "error": int(status == "error")}, "percent_correct": 0}]
    monkeypatch.setattr(cli, "run_cases", fake_run)
    arguments = SimpleNamespace(cases=[ROOT / "evals/cases/actions/hello.json"], repetitions=1, concurrency=4,
        judge=None, live=True, output=tmp_path / "report", changed_since=None)
    with pytest.raises(SystemExit) as exc:
        asyncio.run(cli.run(arguments))
    assert exc.value.code == exit_code
    assert (arguments.output / "report.json").exists()


def test_past_operation_response_is_not_overridden_by_keyword_validation(tmp_path):
    class Adapter:
        async def infer_structured(self, **kwargs):
            response = kwargs["response_model"].model_validate({
                "kind": "respond", "reason": "The user prohibits fresh investigation.", "help_topics": [],
            })
            return SimpleNamespace(content=response.model_dump_json())

    report = asyncio.run(run_case(case("actions/past-operation-count"), adapter=Adapter(),
        judge=None, on_repetition=lambda outcome: None))
    assert report["counts"] == {"correct": 5, "incorrect": 0, "error": 0}


def case(name):
    return RegressionCase.model_validate_json((ROOT / f"evals/cases/{name}.json").read_text())


def test_ten_repetitions_keep_errors_in_denominator_and_reset_context(tmp_path):
    seen = []

    class Adapter:
        async def infer_structured(self, **kwargs):
            seen.append(json.loads(json.dumps(kwargs["messages"])))
            kwargs["messages"].clear()  # An adapter cannot contaminate the next repetition.
            if len(seen) == 9:
                raise InferenceProviderError("offline")
            kind = "tag_proposals"
            if len(seen) <= 8:
                kind = "respond"
            return SimpleNamespace(content=json.dumps({"kind": kind, "reason": "varied wording"}))

    outcomes = []
    report = asyncio.run(run_case(case("actions/hello"), adapter=Adapter(), judge=None, on_repetition=outcomes.append, repetitions=10))
    assert report["counts"] == {"correct": 8, "incorrect": 1, "error": 1}
    assert report["percent_correct"] == 80
    assert len(outcomes) == 10
    assert all(messages == seen[0] for messages in seen)


def test_output_case_generates_and_judges_ten_distinct_outputs(tmp_path):
    judged = []

    class Adapter:
        count = 0

        async def stream_text(self, **kwargs):
            self.count += 1
            yield {"type": "content_delta", "text": f"Answer {self.count}"}
            yield {"type": "done"}

        async def infer_structured(self, **kwargs):
            assert kwargs["response_model"] is OutputJudgment
            payload = json.loads(kwargs["messages"][1]["content"])
            judged.append(payload["candidate_output"])
            return SimpleNamespace(content=json.dumps({"criteria": [
                {"criterion_id": item["id"], "passed": self.count != 10, "reason": "fixture verdict"}
                for item in payload["rubric"]["criteria"]
            ]}))

    judge = JudgeConfig(model="gpt-5.6-luna", thinking_level="off", prompt="Judge criteria")
    report = asyncio.run(run_case(case("faithful-summary"), adapter=Adapter(), judge=judge,
        on_repetition=lambda outcome: None, repetitions=10))
    assert len(set(judged)) == 10
    assert report["percent_correct"] == 90


def test_action_match_checks_args_extra_list_actions_and_types():
    assert matches({"kind": "respond"}, {"kind": "respond", "reason": "Any wording"})
    assert not matches({"tokens": 250000}, {"tokens": 100000})
    assert not matches({"tokens": 1}, {"tokens": True})
    assert not matches([{"kind": "open"}], [{"kind": "open"}, {"kind": "save"}])


def test_export_draft_requires_independent_expectations_and_review(tmp_path):
    fixture = case("actions/hello")
    step = prepare_case(fixture).steps[0]
    invocation = {"kind": step.kind, "model": fixture.model, "thinking_level": fixture.thinking_level,
                  "messages": [message.model_dump() for message in step.messages],
                  "response_model": step.response_model, "response_schema": step.response_schema,
                  "max_output_tokens": step.max_output_tokens}
    history = tmp_path / "history.json"
    history.write_text(json.dumps([[{"schema_version": 1, "invocation": invocation},
                                   {"response": "wrong action"}]]))
    output = tmp_path / "draft.json"
    from_export(SimpleNamespace(history=history, pair=0, output=output))
    draft = RegressionCase.model_validate_json(output.read_text())
    assert not draft.reviewed
    assert draft.steps[0].conversation[-1].content == "Hello!"
    assert "wrong action" not in str(draft.steps[0].expectation)
    assert "wrong action" in str(draft.provenance)
    with pytest.raises(ValueError, match="Review"):
        prepare_case(draft)


def test_judge_missing_criteria_is_an_error_not_a_pass(tmp_path):
    class Adapter:
        async def stream_text(self, **kwargs):
            yield {"type": "content_delta", "text": "An answer"}
            yield {"type": "done"}

        async def infer_structured(self, **kwargs):
            return SimpleNamespace(content=json.dumps({"criteria": [
                {"criterion_id": "facts", "passed": True, "reason": "Only one checked"},
            ]}))

    report = asyncio.run(run_case(case("faithful-summary"), adapter=Adapter(),
        judge=JudgeConfig(model="gpt-5.6-luna", thinking_level="off", prompt="Judge"),
        on_repetition=lambda outcome: None))
    assert report["counts"] == {"correct": 0, "incorrect": 0, "error": 5}
    assert report["percent_correct"] == 0


def test_comparison_rejects_changed_context(tmp_path, capsys):
    before = {"case_id": "case", "case_fingerprint": "same", "judge": {},
              "repetitions": 10, "percent_correct": 60, "counts": {"error": 0}}
    after = {**before, "percent_correct": 80}
    baseline, candidate = tmp_path / "before.json", tmp_path / "after.json"
    baseline.write_text(json.dumps({"cases": [before]}))
    candidate.write_text(json.dumps({"cases": [after]}))
    args = SimpleNamespace(baseline=baseline, candidate=candidate)
    compare(args)
    assert "+20 percentage points" in capsys.readouterr().out
    after["case_fingerprint"] = "different"
    candidate.write_text(json.dumps({"cases": [after]}))
    with pytest.raises(ValueError, match="changed"):
        compare(args)


def test_default_five_repetitions_use_five_as_denominator(tmp_path):
    seen = []
    class Adapter:
        async def infer_structured(self, **kwargs):
            seen.append(kwargs['messages'])
            kind = ['respond', 'respond', 'respond', 'respond', 'investigate_current_scope'][len(seen) - 1]
            return SimpleNamespace(content=json.dumps(dict(kind=kind, help_topics=[], reason='Test')))
    report = asyncio.run(run_case(case('actions/hello'), adapter=Adapter(), judge=None,
        on_repetition=lambda outcome: None))
    assert len(seen) == 5
    assert report['repetitions'] == 5
    assert report['percent_correct'] == 80
    assert report['counts'] == dict(correct=4, incorrect=1, error=0)
