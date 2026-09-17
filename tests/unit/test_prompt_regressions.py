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


ROOT = Path(__file__).resolve().parents[2]


def test_past_operation_response_is_not_overridden_by_keyword_validation(tmp_path):
    class Adapter:
        async def infer_structured(self, **kwargs):
            response = kwargs["response_model"].model_validate({
                "kind": "respond", "reason": "The user prohibits fresh investigation.",
            })
            return SimpleNamespace(content=response.model_dump_json())

    report = asyncio.run(run_case(case("actions/past-operation-count"), adapter=Adapter(),
        judge=None, variant="baseline", directory=tmp_path, on_repetition=lambda outcome: None))
    assert report["counts"] == {"correct": 10, "incorrect": 0, "error": 0}


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
    report = asyncio.run(run_case(case("tagging-question"), adapter=Adapter(), judge=None, variant="baseline",
                                  directory=tmp_path, on_repetition=outcomes.append))
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
        variant="baseline", directory=tmp_path, on_repetition=lambda outcome: None))
    assert len(set(judged)) == 10
    assert report["percent_correct"] == 90


def test_candidate_substitutes_only_explicit_instructions(tmp_path):
    original = case("tagging-question")
    original.steps[0].prompt_bindings[0].file = "candidate.md"
    (tmp_path / "candidate.md").write_text("New system instructions")
    baseline = prepare_case(original, variant="baseline", directory=tmp_path)
    candidate = prepare_case(original, variant="candidate", directory=tmp_path)
    assert candidate.steps[0].messages[0].content == "New system instructions"
    assert baseline.steps[0].messages[0].content != "New system instructions"
    assert candidate.steps[0].messages[1:] == baseline.steps[0].messages[1:]
    original.reviewed = False
    with pytest.raises(ValueError, match="Review"):
        prepare_case(original, variant="baseline", directory=tmp_path)


def test_action_match_checks_args_extra_list_actions_and_types():
    assert matches({"kind": "respond"}, {"kind": "respond", "reason": "Any wording"})
    assert not matches({"tokens": 250000}, {"tokens": 100000})
    assert not matches({"tokens": 1}, {"tokens": True})
    assert not matches([{"kind": "open"}], [{"kind": "open"}, {"kind": "save"}])


def test_skills_do_not_leak_into_later_steps_or_repetitions(tmp_path):
    fixture = case("tagging-question").model_dump()
    step = fixture["steps"][0]
    step["prompt_bindings"] = []
    step["messages"] = [{"role": "system", "content": "SKILL_FOR_THIS_CALL"},
                        {"role": "user", "content": "Hi"}]
    next_step = {**step, "messages": [{"role": "user", "content": "Next"}]}
    fixture["steps"] = [step, next_step]
    seen = []

    class Adapter:
        async def infer_structured(self, **kwargs):
            seen.append(kwargs["messages"])
            return SimpleNamespace(content='{"kind":"respond","reason":"Hello"}')

    asyncio.run(run_case(RegressionCase.model_validate(fixture), adapter=Adapter(), judge=None,
        variant="baseline", directory=tmp_path, on_repetition=lambda outcome: None))
    assert len(seen) == 20
    assert all("SKILL_FOR_THIS_CALL" in json.dumps(messages) for messages in seen[::2])
    assert all("SKILL_FOR_THIS_CALL" not in json.dumps(messages) for messages in seen[1::2])


def test_final_prompt_binding_preserves_evidence_and_schema_drift_fails(tmp_path):
    fixture = case("faithful-summary").model_dump()
    step = fixture["steps"][0]
    step["messages"][-1]["content"] = 'FINAL_RESPONSE_REQUEST\n{"instruction":"old","evidence":"keep exactly"}'
    step["prompt_bindings"] = [{"message_index": 1, "target": "json_instruction",
                                "file": "final.md", "variables": {"basis": "notes"}}]
    (tmp_path / "final.md").write_text("Use {basis} carefully.")
    prepared = prepare_case(RegressionCase.model_validate(fixture), variant="candidate", directory=tmp_path)
    payload = json.loads(prepared.steps[0].messages[1].content.split("\n", 1)[1])
    assert payload == {"instruction": "Use notes carefully.", "evidence": "keep exactly"}
    fixture = case("tagging-question")
    fixture.steps[0].response_schema = {}
    with pytest.raises(ValueError, match="schema changed"):
        prepare_case(fixture, variant="baseline", directory=tmp_path)


def test_export_draft_requires_independent_expectations_and_review(tmp_path):
    fixture = case("tagging-question")
    step = fixture.steps[0]
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
    assert draft.steps[0].current_user_request == "How do tag proposals work?"
    assert "wrong action" not in str(draft.steps[0].expectation)
    assert "wrong action" in str(draft.provenance)
    with pytest.raises(ValueError, match="Review"):
        prepare_case(draft, variant="baseline", directory=tmp_path)


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
        variant="baseline", directory=tmp_path, on_repetition=lambda outcome: None))
    assert report["counts"] == {"correct": 0, "incorrect": 0, "error": 10}
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
