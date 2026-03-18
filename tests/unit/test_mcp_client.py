from __future__ import annotations

import json
import subprocess
import mcp_client
import pytest


def test_reset_local_ollama_server_skips_when_pkill_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(mcp_client.shutil, "which", lambda command_name: None)
    mcp_client._OLLAMA_SIDECAR_PROCESS = object()

    def _unexpected_run(**kwargs):
        raise AssertionError("subprocess.run should not be called when pkill is unavailable")

    monkeypatch.setattr(mcp_client.subprocess, "run", _unexpected_run)

    mcp_client.reset_local_ollama_server(
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
    )

    captured = capsys.readouterr()
    assert "Skipping Ollama reset" in captured.err
    assert "unavailable" in captured.err
    assert mcp_client._OLLAMA_SIDECAR_PROCESS is None


def test_reset_local_ollama_server_skips_on_unexpected_pkill_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(mcp_client.shutil, "which", lambda command_name: "/usr/bin/pkill")
    mcp_client._OLLAMA_SIDECAR_PROCESS = object()

    monkeypatch.setattr(
        mcp_client.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["pkill", "-f", "ollama serve"],
            returncode=3,
            stdout="",
            stderr="sysmond service not found",
        ),
    )

    mcp_client.reset_local_ollama_server(
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
    )

    captured = capsys.readouterr()
    assert "Skipping Ollama reset" in captured.err
    assert "failed with code 3" in captured.err
    assert "sysmond service not found" in captured.err
    assert mcp_client._OLLAMA_SIDECAR_PROCESS is None


def test_agent_error_action_returns_structured_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_tools_list",
        lambda *, url, request_id: {
            "result": {
                "tools": [],
            }
        },
    )
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "llama3.1:latest",
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: (
            {
                "action": "error",
                "detail": "I cannot determine birthday from available notes.",
            },
            '{"action":"error","detail":"I cannot determine birthday from available notes."}',
        ),
    )

    result = mcp_client._run_agentic_request(
        user_message="What is my birthday?",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="llama3.1",
        max_steps=3,
        planner_only=False,
        progress_callback=None,
    )

    assert result["ok"] is False
    assert "cannot determine birthday" in result["answer"]
    assert any(step.get("action") == "agent_error" for step in result["steps"])


def test_unknown_agent_action_returns_structured_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_tools_list",
        lambda *, url, request_id: {
            "result": {
                "tools": [],
            }
        },
    )
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "llama3.1:latest",
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: (
            {
                "action": "nonsense_action",
            },
            '{"action":"nonsense_action"}',
        ),
    )

    result = mcp_client._run_agentic_request(
        user_message="What is my birthday?",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="llama3.1",
        max_steps=3,
        planner_only=False,
        progress_callback=None,
    )

    assert result["ok"] is False
    assert "unsupported action" in result["answer"]
    assert any(step.get("action") == "invalid_decision" for step in result["steps"])


def test_agent_hypothesizes_tags_before_agent_loop(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_tools_list",
        lambda *, url, request_id: {
            "result": {
                "tools": [
                    {"name": "list_tags", "description": "", "inputSchema": {}},
                    {"name": "search_notes", "description": "", "inputSchema": {}},
                ],
            }
        },
    )

    called = {"tool_calls": 0}

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        called["tool_calls"] += 1
        raise RuntimeError(f"Unexpected tool call: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "llama3.1:latest",
    )
    decisions = iter(
        [
            {
                "reasoning": "Likely tags involve dad and birthday terms.",
                "hypothesized_tags": ["dad", "birthday", "biographical-information"],
            },
            {
                "action": "final",
                "answer": "no match",
            },
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: (
            next(decisions),
            "{}",
        ),
    )

    result = mcp_client._run_agentic_request(
        user_message="When is my Dad's birthday?",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="llama3.1",
        max_steps=3,
        planner_only=False,
        progress_callback=None,
    )

    assert result["ok"] is True
    assert result["answer"] == "no match"
    assert result["model"] == "llama3.1:latest"
    assert called["tool_calls"] == 0
    assert result["steps"][0]["action"] == "model_plan"
    assert result["steps"][0]["model_payload"]["hypothesized_tags"] == [
        "dad",
        "birthday",
        "biographical-information",
    ]
    assert result["steps"][1]["action"] == "agent_prompt"


def test_planner_only_returns_after_model_plan(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_tools_list",
        lambda *, url, request_id: (_ for _ in ()).throw(RuntimeError("tools/list should not run in planner_only")),
    )
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: (
            {
                "reasoning": "Likely family tags.",
                "hypothesized_tags": ["dad", "birthday"],
            },
            "{}",
        ),
    )
    monkeypatch.setattr(
        mcp_client,
        "_tools_call",
        lambda *, url, request_id, tool_name, arguments: {
            "result": {
                "structuredContent": {
                    "ok": True,
                    "data": {
                        "prefix": arguments["prefix"],
                        "limit": arguments["limit"],
                        "total_matches": 3,
                        "returned_count": 3,
                        "tags": [
                            {"tag": "dad", "count": 28},
                            {"tag": "birthday", "count": 329},
                            {"tag": "family", "count": 22},
                        ],
                    },
                }
            }
        },
    )

    result = mcp_client._run_agentic_request(
        user_message="When is my dad's birthday?",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=3,
        planner_only=True,
        progress_callback=None,
    )

    assert result["ok"] is True
    assert result["mode"] == "planner_only"
    assert result["answer"] == "dad, birthday"
    assert len(result["steps"]) == 3
    assert result["steps"][0]["action"] == "tag_seed_context"
    assert result["steps"][1]["action"] == "model_plan"
    assert result["steps"][2]["action"] == "tag_catalog_match"
    tag_match_data = result["steps"][2]["tool_response"]["data"]
    assert tag_match_data["resolved_tags"] == ["dad", "birthday"]


def test_normalize_query_hypothesis_allows_up_to_24_tags() -> None:
    payload = {
        "reasoning": "Many possible retrieval anchors and variants.",
        "hypothesized_tags": [f"tag-{index}" for index in range(1, 40)],
    }

    normalized = mcp_client._normalize_query_hypothesis(payload=payload)

    assert len(normalized["hypothesized_tags"]) == 24
    assert normalized["hypothesized_tags"][0] == "tag-1"
    assert normalized["hypothesized_tags"][-1] == "tag-24"


def test_normalize_expression_plan_filters_cross_language_when_query_is_ascii() -> None:
    payload = {
        "reasoning": "Try variants",
        "expressions": [
            {"type": "phrase", "value": "social security number"},
            {"type": "phrase", "value": "社会保障号码"},
            {"type": "regex", "pattern": "[0-9]{3}-[0-9]{2}-[0-9]{4}", "flags": "ims"},
            {"type": "regex", "pattern": "社会保障", "flags": "ims"},
        ],
    }

    normalized = mcp_client._normalize_expression_plan(
        payload=payload,
        max_expressions=20,
        min_expressions=1,
        source_message="What is my social security number?",
    )

    assert normalized["expressions"] == [
        {"type": "phrase", "value": "social security number"},
        {"type": "regex", "pattern": "[0-9]{3}-[0-9]{2}-[0-9]{4}", "flags": "ims"},
    ]


def test_normalize_expression_plan_rejects_only_conjunctive_label_value_regex() -> None:
    payload = {
        "reasoning": "Single combined regex",
        "expressions": [
            {
                "type": "regex",
                "pattern": "(?:label|alias).*[0-9]{3}-[0-9]{2}-[0-9]{4}",
                "flags": "ims",
            }
        ],
    }

    with pytest.raises(ValueError, match="over-constrains label/value co-location"):
        mcp_client._normalize_expression_plan(
            payload=payload,
            max_expressions=20,
            min_expressions=1,
            source_message="What is my id number?",
        )


def test_normalize_expression_plan_accepts_mixed_regex_when_standalone_value_regex_present() -> None:
    payload = {
        "reasoning": "Conjunctive and standalone value regex",
        "expressions": [
            {
                "type": "regex",
                "pattern": "(?:label|alias).*[0-9]{3}-[0-9]{2}-[0-9]{4}",
                "flags": "ims",
            },
            {
                "type": "regex",
                "pattern": "[0-9]{3}-[0-9]{2}-[0-9]{4}",
                "flags": "ims",
            },
        ],
    }

    normalized = mcp_client._normalize_expression_plan(
        payload=payload,
        max_expressions=20,
        min_expressions=1,
        source_message="What is my id number?",
    )

    assert len(normalized["expressions"]) == 2


def test_normalize_expression_plan_accepts_near_atom() -> None:
    payload = {
        "reasoning": "Use nearby anchors",
        "expressions": [
            {"type": "near", "left": "mom", "right": "birthday", "window_chars": 200},
        ],
    }

    normalized = mcp_client._normalize_expression_plan(
        payload=payload,
        max_expressions=20,
        min_expressions=1,
        source_message="When is my mom's birthday?",
    )

    assert normalized["expressions"] == [
        {"type": "near", "left": "mom", "right": "birthday", "window_chars": 200},
    ]


def test_normalize_expression_plan_filters_question_like_phrases() -> None:
    payload = {
        "reasoning": "Question-style phrase should be dropped.",
        "expressions": [
            {"type": "phrase", "value": "When is my mom's birthday?"},
            {"type": "phrase", "value": "mom's birthday"},
        ],
    }

    normalized = mcp_client._normalize_expression_plan(
        payload=payload,
        max_expressions=20,
        min_expressions=1,
        source_message="When is my mom's birthday?",
    )

    assert normalized["expressions"] == [
        {"type": "phrase", "value": "mom's birthday"},
    ]


def test_normalize_expression_plan_allows_phrase_only_for_structured_value_queries() -> None:
    payload = {
        "reasoning": "Only phrase anchors",
        "expressions": [
            {"type": "phrase", "value": "social security number"},
            {"type": "phrase", "value": "ssn"},
        ],
    }

    normalized = mcp_client._normalize_expression_plan(
        payload=payload,
        max_expressions=20,
        min_expressions=1,
        source_message="What is my social security number?",
    )
    assert normalized["expressions"] == payload["expressions"]


def test_normalize_expression_plan_allows_non_numeric_regex_for_structured_value_queries() -> None:
    payload = {
        "reasoning": "Only label regexes",
        "expressions": [
            {"type": "phrase", "value": "social security number"},
            {"type": "regex", "pattern": "(?:social security number|ssn)", "flags": "ims"},
            {"type": "regex", "pattern": "identifier|account number", "flags": "ims"},
        ],
    }

    normalized = mcp_client._normalize_expression_plan(
        payload=payload,
        max_expressions=20,
        min_expressions=1,
        source_message="What is my social security number?",
    )
    assert normalized["expressions"] == payload["expressions"]


def test_normalize_expression_plan_rejects_regexy_near_anchors() -> None:
    payload = {
        "reasoning": "Near with regex syntax should be dropped.",
        "expressions": [
            {"type": "near", "left": "[Ss]sn", "right": ":", "window_chars": 200},
            {"type": "near", "left": "mom", "right": "birthday", "window_chars": 200},
        ],
    }

    normalized = mcp_client._normalize_expression_plan(
        payload=payload,
        max_expressions=20,
        min_expressions=1,
        source_message="When is my mom's birthday?",
    )
    assert normalized["expressions"] == [
        {"type": "near", "left": "mom", "right": "birthday", "window_chars": 200},
    ]


def test_match_hypothesized_tags_to_catalog_returns_exact_and_fuzzy() -> None:
    match_data = mcp_client._match_hypothesized_tags_to_catalog(
        hypothesized_tags=["dad", "nightmares", "sleep"],
        tag_entries=[
            {"tag": "dad", "count": 8},
            {"tag": "nightmare", "count": 3},
            {"tag": "sleep", "count": 5},
            {"tag": "dream", "count": 4},
        ],
    )

    exact_catalog_tags = [entry["catalog_tag"] for entry in match_data["exact_matches"]]
    assert "dad" in exact_catalog_tags
    assert "sleep" in exact_catalog_tags
    fuzzy_pairs = [
        (entry["hypothesis"], entry["catalog_tag"])
        for entry in match_data["fuzzy_matches"]
    ]
    assert ("nightmares", "nightmare") in fuzzy_pairs
    assert "nightmares" not in match_data["unmatched_hypothesized_tags"]


def test_match_hypothesized_tags_to_catalog_rejects_noisy_partial_overlap() -> None:
    match_data = mcp_client._match_hypothesized_tags_to_catalog(
        hypothesized_tags=["field-research", "surveys", "social-sciences"],
        tag_entries=[
            {"tag": "Field-of-Glory", "count": 12},
            {"tag": "scurvy", "count": 2},
            {"tag": "field-research", "count": 4},
            {"tag": "social-media", "count": 100},
        ],
    )

    fuzzy_pairs = {
        (entry["hypothesis"], entry["catalog_tag"])
        for entry in match_data["fuzzy_matches"]
    }
    assert ("field-research", "Field-of-Glory") not in fuzzy_pairs
    assert ("surveys", "scurvy") not in fuzzy_pairs
    assert ("social-sciences", "social-media") not in fuzzy_pairs
    exact_catalog_tags = [entry["catalog_tag"] for entry in match_data["exact_matches"]]
    assert "field-research" in exact_catalog_tags
    assert "surveys" in match_data["unmatched_hypothesized_tags"]
    assert "social-sciences" in match_data["unmatched_hypothesized_tags"]


def test_match_hypothesized_tags_to_catalog_matches_papers_to_paper() -> None:
    match_data = mcp_client._match_hypothesized_tags_to_catalog(
        hypothesized_tags=["papers"],
        tag_entries=[
            {"tag": "paper", "count": 3},
            {"tag": "papers-with-code", "count": 120},
            {"tag": "two-minute-papers", "count": 90},
            {"tag": "Google-Research", "count": 400},
            {"tag": "Microsoft-Research", "count": 350},
        ],
    )

    fuzzy_pairs = {
        (entry["hypothesis"], entry["catalog_tag"])
        for entry in match_data["fuzzy_matches"]
    }
    assert ("papers", "paper") in fuzzy_pairs


def test_match_hypothesized_tags_to_catalog_keeps_fuzzy_when_exact_exists() -> None:
    match_data = mcp_client._match_hypothesized_tags_to_catalog(
        hypothesized_tags=["papers"],
        tag_entries=[
            {"tag": "papers", "count": 50},
            {"tag": "paper", "count": 10},
            {"tag": "two-minute-papers", "count": 90},
        ],
    )

    exact_catalog_tags = [entry["catalog_tag"] for entry in match_data["exact_matches"]]
    assert "papers" in exact_catalog_tags
    fuzzy_pairs = {
        (entry["hypothesis"], entry["catalog_tag"])
        for entry in match_data["fuzzy_matches"]
    }
    assert ("papers", "paper") in fuzzy_pairs
    assert ("papers", "two-minute-papers") not in fuzzy_pairs


def test_match_hypothesized_tags_to_catalog_blocks_directional_expansion() -> None:
    match_data = mcp_client._match_hypothesized_tags_to_catalog(
        hypothesized_tags=["topic", "field"],
        tag_entries=[
            {"tag": "topic-modeling", "count": 200},
            {"tag": "topics", "count": 25},
            {"tag": "Field-of-Glory", "count": 50},
        ],
    )

    fuzzy_pairs = {
        (entry["hypothesis"], entry["catalog_tag"])
        for entry in match_data["fuzzy_matches"]
    }
    assert ("topic", "topic-modeling") not in fuzzy_pairs
    assert ("field", "Field-of-Glory") not in fuzzy_pairs
    assert ("topic", "topics") in fuzzy_pairs


def test_planner_only_exact_matches_include_seed_membership_split(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_tools_list",
        lambda *, url, request_id: (_ for _ in ()).throw(RuntimeError("tools/list should not run in planner_only")),
    )
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: (
            {
                "reasoning": "Likely family + sleep tags.",
                "hypothesized_tags": ["dad", "sleep"],
            },
            "{}",
        ),
    )

    call_count = {"list_tags": 0}

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name != "list_tags":
            raise RuntimeError(f"Unexpected tool call: {tool_name}")
        call_count["list_tags"] += 1
        if call_count["list_tags"] == 1:
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "prefix": arguments["prefix"],
                            "limit": arguments["limit"],
                            "total_matches": 2,
                            "returned_count": 2,
                            "tags": [
                                {"tag": "dad", "count": 28},
                                {"tag": "birthday", "count": 329},
                            ],
                        },
                    }
                }
            }
        return {
            "result": {
                "structuredContent": {
                    "ok": True,
                    "data": {
                        "prefix": arguments["prefix"],
                        "limit": arguments["limit"],
                        "total_matches": 3,
                        "returned_count": 3,
                        "tags": [
                            {"tag": "dad", "count": 28},
                            {"tag": "birthday", "count": 329},
                            {"tag": "sleep", "count": 12},
                        ],
                    },
                }
            }
        }

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_agentic_request(
        user_message="When did I sleep and talk to dad?",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=3,
        planner_only=True,
        progress_callback=None,
    )

    assert result["ok"] is True
    tag_match_data = result["steps"][2]["tool_response"]["data"]
    assert tag_match_data["exact_matches_from_seed"] == ["dad"]
    assert tag_match_data["exact_matches_not_from_seed"] == ["sleep"]
    exact_entries = tag_match_data["exact_matches"]
    from_seed_by_tag = {entry["catalog_tag"]: entry["from_seed"] for entry in exact_entries}
    assert from_seed_by_tag["dad"] is True
    assert from_seed_by_tag["sleep"] is False


def test_invalid_decision_gets_one_repair_attempt(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_tools_list",
        lambda *, url, request_id: {
            "result": {
                "tools": [],
            }
        },
    )
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "llama3.1:latest",
    )
    decisions = iter(
        [
            {
                "reasoning": "Likely tags include dad and birthday.",
                "hypothesized_tags": ["dad", "birthday"],
            },
            {"notes": [{"id": "note-1"}]},
            {"action": "final", "answer": "Done"},
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: (
            next(decisions),
            "{}",
        ),
    )

    result = mcp_client._run_agentic_request(
        user_message="When is my dad's birthday?",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="llama3.1",
        max_steps=3,
        planner_only=False,
        progress_callback=None,
    )

    assert result["ok"] is True
    assert result["answer"] == "Done"
    assert any(step.get("action") == "invalid_decision" for step in result["steps"])


def test_action_as_tool_name_is_accepted(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_tools_list",
        lambda *, url, request_id: {
            "result": {
                "tools": [
                    {"name": "search_notes", "description": "", "inputSchema": {}},
                ],
            }
        },
    )
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    calls = {"search_notes": 0}

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name != "search_notes":
            raise RuntimeError(f"Unexpected tool call: {tool_name}")
        calls["search_notes"] += 1
        return {
            "result": {
                "structuredContent": {
                    "ok": True,
                    "data": {
                        "query": arguments["query"],
                        "required_tags": arguments["required_tags"],
                        "forbidden_tags": arguments["forbidden_tags"],
                        "limit": arguments["limit"],
                        "offset": arguments["offset"],
                        "total_matches": 0,
                        "returned_count": 0,
                        "results": [],
                    },
                }
            }
        }

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)
    decisions = iter(
        [
            {
                "reasoning": "Likely tags include dad and birthday.",
                "hypothesized_tags": ["dad", "birthday"],
            },
            {
                "action": "search_notes",
                "arguments": {
                    "query": "dad birthday",
                    "required_tags": [],
                    "forbidden_tags": [],
                    "limit": 5,
                    "offset": 0,
                },
                "reason": "tool-name action shorthand",
            },
            {
                "action": "final",
                "answer": "No exact match found.",
            },
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: (
            next(decisions),
            "{}",
        ),
    )

    result = mcp_client._run_agentic_request(
        user_message="When is my dad's birthday?",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=3,
        planner_only=False,
        progress_callback=None,
    )

    assert result["ok"] is True
    assert result["answer"] == "No exact match found."
    assert calls["search_notes"] == 1
    tool_steps = [step for step in result["steps"] if step.get("action") == "tool"]
    assert len(tool_steps) >= 1
    assert tool_steps[0]["tool_name"] == "search_notes"


def test_compact_for_output_omits_large_data_uri() -> None:
    giant_data_uri = "data:image/png;base64," + ("A" * 4000)
    payload = {
        "ok": True,
        "data": {
            "children": [
                {
                    "note": {
                        "content": f'<img src="{giant_data_uri}" />',
                    }
                }
            ]
        },
    }

    compact = mcp_client._compact_for_output(value=payload)
    assert isinstance(compact, dict)
    data = compact["data"]
    assert isinstance(data, dict)
    children = data["children"]
    assert isinstance(children, list)
    first_child = children[0]
    assert isinstance(first_child, dict)
    note = first_child["note"]
    assert isinstance(note, dict)
    content = note["content"]
    assert isinstance(content, str)
    assert "[image-data-uri-omitted]" in content


def test_bootstrap_intersection_builds_shared_note_candidates(monkeypatch) -> None:
    called = {
        "get_note": 0,
    }

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name == "list_tags":
            prefix = arguments["prefix"]
            if prefix == "dad":
                tags = [
                    {"tag": "dad", "count": 28},
                    {"tag": "dad-work", "count": 4},
                ]
            elif prefix == "birthday":
                tags = [
                    {"tag": "birthday", "count": 329},
                    {"tag": "birthday-party", "count": 8},
                ]
            else:
                tags = []
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "prefix": prefix,
                            "limit": arguments["limit"],
                            "total_matches": len(tags),
                            "returned_count": len(tags),
                            "tags": tags,
                        },
                    }
                }
            }
        if tool_name == "search_notes":
            query = arguments["query"]
            required_tags = arguments["required_tags"]
            if query != "":
                raise RuntimeError("Expected empty free-text query for two-tag bootstrap")
            if required_tags == ["dad", "birthday"]:
                results = [{"note_id": "n-shared", "preview_text": "dad birthday note"}]
            else:
                results = []
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "results": results,
                        },
                    }
                }
            }
        if tool_name == "get_note":
            called["get_note"] += 1
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "note": {
                                "id": arguments["note_id"],
                                "parent_id": None,
                                "content": "Dad birthday: March 30, 1946",
                            },
                            "tags": {
                                "tag_terms": ["dad", "birthday"],
                                "effective_tag_terms": ["dad", "birthday", "biographical-information"],
                            },
                            "children": [],
                        },
                    }
                }
            }
        raise RuntimeError(f"Unexpected tool call: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    payload = mcp_client._bootstrap_intersection_steps(
        user_message="When is my dad's birthday?",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        request_id=10,
    )

    assert payload["next_request_id"] > 10
    steps = payload["steps"]
    assert len(steps) >= 1
    summary_step = steps[-1]
    assert summary_step["action"] == "bootstrap_intersection"
    summary_data = summary_step["tool_response"]["data"]
    assert summary_data["intersection_count"] == 1
    assert summary_data["intersection_note_ids"] == ["n-shared"]
    assert summary_data["hydrated_note_ids"] == [
        {
            "note_id": "n-shared",
            "combo_hit_count": 1,
        }
    ]
    assert called["get_note"] == 1


def test_sanitize_search_notes_arguments_fold_tag_arrays_into_query() -> None:
    tool_summaries = [
        {
            "name": "search_notes",
            "description": "",
            "inputSchema": {},
        }
    ]
    sanitize_result = mcp_client._sanitize_tool_arguments(
        tool_name="search_notes",
        arguments={
            "query": "",
            "required_tags": ["dad", "birthday"],
            "forbidden_tags": ["draft"],
            "limit": 5,
            "offset": 0,
        },
        tool_summaries=tool_summaries,
    )

    assert sanitize_result["ok"] is True
    assert sanitize_result["changed"] is True
    normalized_arguments = sanitize_result["arguments"]
    assert normalized_arguments["query"] == "dad birthday -draft"
    assert normalized_arguments["required_tags"] == []
    assert normalized_arguments["forbidden_tags"] == []


def test_duplicate_semantic_search_notes_call_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_tools_list",
        lambda *, url, request_id: {
            "result": {
                "tools": [
                    {"name": "search_notes", "description": "", "inputSchema": {}},
                ],
            }
        },
    )
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    calls = {"search_notes": 0}

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name != "search_notes":
            raise RuntimeError(f"Unexpected tool call: {tool_name}")
        calls["search_notes"] += 1
        return {
            "result": {
                "structuredContent": {
                    "ok": True,
                    "data": {
                        "query": arguments["query"],
                        "required_tags": arguments["required_tags"],
                        "forbidden_tags": arguments["forbidden_tags"],
                        "limit": arguments["limit"],
                        "offset": arguments["offset"],
                        "total_matches": 0,
                        "returned_count": 0,
                        "results": [],
                    },
                }
            }
        }

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)
    decisions = iter(
        [
            {
                "reasoning": "Likely tags include dad and birthday.",
                "hypothesized_tags": ["dad", "birthday"],
            },
            {
                "action": "tool",
                "tool_name": "search_notes",
                "arguments": {
                    "query": "dad birthday",
                    "required_tags": [],
                    "forbidden_tags": [],
                    "limit": 5,
                    "offset": 0,
                },
                "reason": "First attempt.",
            },
            {
                "action": "tool",
                "tool_name": "search_notes",
                "arguments": {
                    "query": "birthday dad",
                    "required_tags": [],
                    "forbidden_tags": [],
                    "limit": 5,
                    "offset": 0,
                },
                "reason": "Duplicate attempt.",
            },
            {
                "action": "final",
                "answer": "No match.",
            },
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: (
            next(decisions),
            "{}",
        ),
    )

    result = mcp_client._run_agentic_request(
        user_message="When is my dad's birthday?",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=5,
        planner_only=False,
        progress_callback=None,
    )

    assert result["ok"] is True
    assert calls["search_notes"] == 1
    tool_steps = [
        step
        for step in result["steps"]
        if step.get("action") == "tool" and step.get("tool_name") == "search_notes"
    ]
    assert len(tool_steps) == 2
    assert tool_steps[1]["tool_response"]["ok"] is False
    assert "Duplicate search strategy" in tool_steps[1]["tool_response"]["error"]


def test_compact_json_payload_keeps_scalar_leaf_values_at_depth_zero() -> None:
    payload = {
        "root": {
            "branch": {
                "leaf_values": ["dad", "birthday", "email"],
            }
        }
    }
    compact = mcp_client._compact_json_payload(
        value=payload,
        max_depth=4,
        max_list_items=10,
        max_dict_items=10,
        max_string_chars=200,
    )

    assert compact["root"]["branch"]["leaf_values"] == ["dad", "birthday", "email"]


def test_run_rewrite_global_universe_uses_count_notes_and_skips_universe_stage(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    model_calls = iter(
        [
            (
                {
                    "reasoning": "Use phrase and lexical variants.",
                    "expressions": [
                        {"type": "phrase", "value": "dad birthday"},
                        {"type": "phrase", "value": "dad's birthday"},
                        {"type": "phrase", "value": "father birthday"},
                        {"type": "phrase", "value": "dad bday"},
                        {"type": "phrase", "value": "birthday dad"},
                    ],
                },
                '{"reasoning":"Use phrase and lexical variants.","expressions":[{"type":"phrase","value":"dad birthday"},{"type":"phrase","value":"dad\\u0027s birthday"},{"type":"phrase","value":"father birthday"},{"type":"phrase","value":"dad bday"},{"type":"phrase","value":"birthday dad"}]}',
            ),
            (
                {
                    "reasoning": "First query already returned enough direct hits.",
                    "decision": "answer",
                    "answer": "No answer found.",
                    "confidence": "low",
                    "continue_reason": "",
                    "clarifying_question": "",
                },
                '{"reasoning":"First query already returned enough direct hits.","decision":"answer","answer":"No answer found.","confidence":"low","continue_reason":"","clarifying_question":""}',
            ),
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: next(model_calls),
    )

    tool_calls = []

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        tool_calls.append((tool_name, arguments))
        if tool_name == "count_notes":
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {"total_notes": 500},
                    }
                }
            }
        if tool_name == "search_notes":
            query = arguments["query"]
            if not isinstance(query, str):
                raise AssertionError("search_notes query must be a string")
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "query": query,
                            "required_tags": [],
                            "forbidden_tags": [],
                            "resolved_query": query,
                            "limit": arguments["limit"],
                            "offset": 0,
                            "total_matches": 2,
                            "returned_count": 2,
                            "results": [
                                {
                                    "note_id": "n1",
                                    "preview_text": "dad birthday one",
                                    "content_text": "dad birthday one",
                                    "context_text": "dad birthday one",
                                    "tag_terms": ["dad"],
                                    "effective_tag_terms": ["dad", "birthday"],
                                },
                                {
                                    "note_id": "n2",
                                    "preview_text": "dad birthday two",
                                    "content_text": "dad birthday two",
                                    "context_text": "dad birthday two",
                                    "tag_terms": ["dad", "birthday"],
                                    "effective_tag_terms": ["dad", "birthday"],
                                },
                            ],
                        },
                    }
                }
            }
        raise AssertionError(f"Unexpected tool: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_rewrite_request(
        user_message="When is my dad's birthday?",
        search_context_query="",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=6,
        max_expressions=5,
        hydrate_top_k=20,
        regex_engine="python-re",
        progress_callback=None,
    )

    assert result["ok"] is True
    assert result["steps"][0]["action"] == "run_config"
    assert result["steps"][1]["action"] == "expression_plan"
    assert all(step["action"] != "universe_resolve" for step in result["steps"])

    run_config_data = result["steps"][0]["tool_response"]["data"]
    assert run_config_data["universe_mode"] == "global"
    assert run_config_data["universe_boundary_tool"] == "count_notes"
    assert run_config_data["universe_note_count"] == 500
    assert isinstance(result["total_execution_ms"], float)
    assert result["total_execution_ms"] >= 0.0

    expression_step = next(
        step for step in result["steps"] if step.get("action") == "expression_execute"
    )
    assert expression_step["arguments"]["query"] == '"dad birthday"'
    assert tool_calls[0][0] == "count_notes"


def test_run_rewrite_scoped_universe_uses_search_context_boundary(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    model_calls = iter(
        [
            (
                {
                    "reasoning": "Use phrase variants.",
                    "expressions": [
                        {"type": "phrase", "value": "dad birthday"},
                        {"type": "phrase", "value": "dad's birthday"},
                        {"type": "phrase", "value": "mom dad birthday"},
                        {"type": "phrase", "value": "birthday dad"},
                        {"type": "phrase", "value": "dad bday"},
                    ],
                },
                '{"reasoning":"Use phrase variants.","expressions":[{"type":"phrase","value":"dad birthday"},{"type":"phrase","value":"dad\\u0027s birthday"},{"type":"phrase","value":"mom dad birthday"},{"type":"phrase","value":"birthday dad"},{"type":"phrase","value":"dad bday"}]}',
            ),
            (
                {
                    "reasoning": "Scoped result is enough to answer.",
                    "decision": "answer",
                    "answer": "Scoped answer.",
                    "confidence": "medium",
                    "continue_reason": "",
                    "clarifying_question": "",
                },
                '{"reasoning":"Scoped result is enough to answer.","decision":"answer","answer":"Scoped answer.","confidence":"medium","continue_reason":"","clarifying_question":""}',
            ),
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: next(model_calls),
    )

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name == "search_note_ids" and arguments["query"] == "work-journal -private":
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "query": arguments["query"],
                            "required_tags": [],
                            "forbidden_tags": [],
                            "resolved_query": arguments["query"],
                            "limit": arguments["limit"],
                            "offset": 0,
                            "total_matches": 2,
                            "returned_count": 2,
                            "note_ids": ["u1", "u2"],
                        },
                    }
                }
            }
        if tool_name == "search_notes" and arguments["query"] == '"dad birthday"':
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "query": arguments["query"],
                            "required_tags": [],
                            "forbidden_tags": [],
                            "resolved_query": arguments["query"],
                            "limit": arguments["limit"],
                            "offset": 0,
                            "total_matches": 2,
                            "returned_count": 2,
                            "results": [
                                {
                                    "note_id": "u2",
                                    "preview_text": "u2 dad birthday",
                                    "content_text": "u2 dad birthday",
                                    "context_text": "u2 dad birthday",
                                    "tag_terms": ["dad", "birthday"],
                                    "effective_tag_terms": ["dad", "birthday"],
                                },
                                {
                                    "note_id": "x1",
                                    "preview_text": "x1 dad birthday",
                                    "content_text": "x1 dad birthday",
                                    "context_text": "x1 dad birthday",
                                    "tag_terms": ["dad"],
                                    "effective_tag_terms": ["dad", "birthday"],
                                },
                            ],
                        },
                    }
                }
            }
        if tool_name == "search_notes":
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "query": arguments["query"],
                            "required_tags": [],
                            "forbidden_tags": [],
                            "resolved_query": arguments["query"],
                            "limit": arguments["limit"],
                            "offset": 0,
                            "total_matches": 1,
                            "returned_count": 1,
                            "results": [
                                {
                                    "note_id": "u2",
                                    "preview_text": "u2 only",
                                    "content_text": "u2 only",
                                    "context_text": "u2 only",
                                    "tag_terms": [],
                                    "effective_tag_terms": [],
                                }
                            ],
                        },
                    }
                }
            }
        raise AssertionError(f"Unexpected tool call: {tool_name} {arguments}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_rewrite_request(
        user_message="When is my dad's birthday?",
        search_context_query="work-journal -private",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=6,
        max_expressions=5,
        hydrate_top_k=20,
        regex_engine="python-re",
        progress_callback=None,
    )

    assert result["ok"] is True
    run_config_data = result["steps"][0]["tool_response"]["data"]
    assert run_config_data["universe_mode"] == "scoped"
    assert run_config_data["universe_boundary_tool"] == "search_note_ids"
    assert run_config_data["universe_boundary_arguments"]["query"] == "work-journal -private"
    assert isinstance(result["total_execution_ms"], float)
    assert result["total_execution_ms"] >= 0.0

    expression_step = next(
        step for step in result["steps"] if step.get("action") == "expression_execute"
    )
    assert expression_step["stats"]["scoped_match_count"] == 1


def test_run_rewrite_expression_plan_repairs_underproduced_model_output(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    model_calls = iter(
        [
            (
                {
                    "reasoning": "Initial draft with enough expressions for a first pass.",
                    "expressions": [
                        {"type": "phrase", "value": "mom birthday"},
                        {"type": "phrase", "value": "mom's birthday"},
                        {"type": "phrase", "value": "mother birthday"},
                    ],
                },
                '{"reasoning":"Initial draft with enough expressions for a first pass.","expressions":[{"type":"phrase","value":"mom birthday"},{"type":"phrase","value":"mom\\u0027s birthday"},{"type":"phrase","value":"mother birthday"}]}',
            ),
            (
                {
                    "reasoning": "Direct evidence is already sufficient.",
                    "decision": "answer",
                    "answer": "Her birthday is January 16.",
                    "confidence": "high",
                    "continue_reason": "",
                    "clarifying_question": "",
                },
                '{"reasoning":"Direct evidence is already sufficient.","decision":"answer","answer":"Her birthday is January 16.","confidence":"high","continue_reason":"","clarifying_question":""}',
            ),
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: next(model_calls),
    )

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name == "count_notes":
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {"total_notes": 500},
                    }
                }
            }
        if tool_name == "search_notes":
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "query": arguments["query"],
                            "required_tags": [],
                            "forbidden_tags": [],
                            "resolved_query": arguments["query"],
                            "limit": arguments["limit"],
                            "offset": 0,
                            "total_matches": 1,
                            "returned_count": 1,
                            "results": [
                                {
                                    "note_id": "n1",
                                    "preview_text": "2023.01.16 - Mom's birthday lunch at Saffron",
                                    "content_text": "2023.01.16 - Mom's birthday lunch at Saffron",
                                    "context_text": "2023.01.16 - Mom's birthday lunch at Saffron",
                                    "tag_terms": ["mom", "birthday"],
                                    "effective_tag_terms": ["mom", "birthday"],
                                }
                            ],
                        },
                    }
                }
            }
        raise AssertionError(f"Unexpected tool call: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_rewrite_request(
        user_message="When is my mom's birthday?",
        search_context_query="",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=6,
        max_expressions=20,
        hydrate_top_k=10,
        regex_engine="python-re",
        progress_callback=None,
    )

    assert result["ok"] is True
    run_config = result["steps"][0]["tool_response"]["data"]
    assert run_config["expression_target_count"] == 8
    assert "expression_min_required" not in run_config
    assert run_config["expression_probe_points"] == [4, 8]

    first_plan = result["steps"][1]
    assert first_plan["action"] == "expression_plan"
    assert first_plan["model_payload"]["accepted"] is True
    assert all(step.get("action") != "expression_plan_repair" for step in result["steps"])


def test_run_rewrite_uses_partial_model_plan_instead_of_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    model_calls = iter(
        [
            (
                {
                    "reasoning": "Initial short draft.",
                    "expressions": [{"type": "phrase", "value": "social security number"}],
                },
                '{"reasoning":"Initial short draft.","expressions":[{"type":"phrase","value":"social security number"}]}',
            ),
            (
                {
                    "reasoning": "First pass evidence is enough.",
                    "decision": "answer",
                    "answer": "Use retrieved evidence.",
                    "confidence": "medium",
                    "continue_reason": "",
                    "clarifying_question": "",
                },
                '{"reasoning":"First pass evidence is enough.","decision":"answer","answer":"Use retrieved evidence.","confidence":"medium","continue_reason":"","clarifying_question":""}',
            ),
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: next(model_calls),
    )

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name == "count_notes":
            return {"result": {"structuredContent": {"ok": True, "data": {"total_notes": 100}}}}
        if tool_name == "search_notes":
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "query": arguments["query"],
                            "required_tags": [],
                            "forbidden_tags": [],
                            "resolved_query": arguments["query"],
                            "limit": arguments["limit"],
                            "offset": arguments["offset"],
                            "total_matches": 1,
                            "returned_count": 1,
                            "results": [
                                {
                                    "note_id": "n1",
                                    "preview_text": "social security number: 123-45-6789",
                                    "content_text": "social security number: 123-45-6789",
                                    "context_text": "social security number: 123-45-6789",
                                    "tag_terms": ["ssn"],
                                    "effective_tag_terms": ["ssn", "security"],
                                }
                            ],
                        },
                    }
                }
            }
        raise AssertionError(f"Unexpected tool call: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_rewrite_request(
        user_message="What is my social security number?",
        search_context_query="",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=6,
        max_expressions=20,
        hydrate_top_k=10,
        regex_engine="python-re",
        progress_callback=None,
    )

    assert result["ok"] is True
    assert all(step.get("action") != "expression_plan_repair" for step in result["steps"])
    assert all(step.get("action") != "expression_plan_partial_accept" for step in result["steps"])
    assert all(step.get("action") != "expression_plan_fallback" for step in result["steps"])


def test_run_rewrite_fails_fast_when_planner_returns_no_usable_expressions(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    model_calls = iter(
        [
            (
                {
                    "reasoning": "No usable expressions",
                    "expressions": [],
                },
                '{"reasoning":"No usable expressions","expressions":[]}',
            ),
            (
                {
                    "reasoning": "Still no usable expressions",
                    "expressions": [],
                },
                '{"reasoning":"Still no usable expressions","expressions":[]}',
            ),
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: next(model_calls),
    )

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name == "count_notes":
            return {"result": {"structuredContent": {"ok": True, "data": {"total_notes": 100}}}}
        raise AssertionError(f"Unexpected tool call after planning failure: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_rewrite_request(
        user_message="What is my social security number?",
        search_context_query="",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=6,
        max_expressions=20,
        hydrate_top_k=10,
        regex_engine="python-re",
        progress_callback=None,
    )

    assert result["ok"] is False
    assert "Expression planning failed" in result["answer"]
    assert any(step.get("action") == "expression_plan_error" for step in result["steps"])


def test_run_rewrite_prioritizes_regex_before_phrase_for_structured_queries(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    model_calls = iter(
        [
            (
                {
                    "reasoning": "Use label phrase and value regex.",
                    "expressions": [
                        {"type": "phrase", "value": "social security number"},
                        {"type": "regex", "pattern": "[0-9]{3}-[0-9]{2}-[0-9]{4}", "flags": "ims"},
                    ],
                },
                '{"reasoning":"Use label phrase and value regex.","expressions":[{"type":"phrase","value":"social security number"},{"type":"regex","pattern":"[0-9]{3}-[0-9]{2}-[0-9]{4}","flags":"ims"}]}',
            ),
            (
                {
                    "reasoning": "Need one more pass before final answer.",
                    "decision": "continue",
                    "answer": "",
                    "clarifying_question": "",
                    "confidence": "medium",
                    "continue_reason": "Run remaining planned expression.",
                },
                '{"reasoning":"Need one more pass before final answer.","decision":"continue","answer":"","clarifying_question":"","confidence":"medium","continue_reason":"Run remaining planned expression."}',
            ),
            (
                {
                    "reasoning": "Now enough evidence.",
                    "decision": "answer",
                    "answer": "Found one likely match.",
                    "clarifying_question": "",
                    "confidence": "medium",
                    "continue_reason": "",
                },
                '{"reasoning":"Now enough evidence.","decision":"answer","answer":"Found one likely match.","clarifying_question":"","confidence":"medium","continue_reason":""}',
            ),
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: next(model_calls),
    )

    expression_tool_order = []

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name == "count_notes":
            return {"result": {"structuredContent": {"ok": True, "data": {"total_notes": 100}}}}
        if tool_name == "search_notes_regex":
            expression_tool_order.append(tool_name)
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "pattern": arguments["pattern"],
                            "flags": arguments["flags"],
                            "regex_engine": arguments["regex_engine"],
                            "target": arguments["target"],
                            "scope_count": len(arguments.get("scope_note_ids", [])),
                            "limit": arguments["limit"],
                            "offset": arguments["offset"],
                            "total_matches": 1,
                            "returned_count": 1,
                            "note_ids": ["n1"],
                        },
                    }
                }
            }
        if tool_name == "search_notes_regex":
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "pattern": arguments["pattern"],
                            "flags": arguments["flags"],
                            "regex_engine": arguments["regex_engine"],
                            "target": arguments["target"],
                            "scope_count": len(arguments.get("scope_note_ids", [])),
                            "limit": arguments["limit"],
                            "offset": arguments["offset"],
                            "total_matches": 1,
                            "returned_count": 1,
                            "results": [
                                {
                                    "note_id": "n1",
                                    "preview_text": "SSN: 123-45-6789",
                                    "content_text": "SSN: 123-45-6789",
                                    "context_text": "ME --- SSN: 123-45-6789",
                                    "tag_terms": ["ssn"],
                                    "effective_tag_terms": ["ssn"],
                                    "matches": [
                                        {
                                            "field": "content_text",
                                            "start": 0,
                                            "end": 11,
                                            "snippet": "123-45-6789",
                                            "normalized_text_match": False,
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                }
            }
        if tool_name == "search_notes":
            expression_tool_order.append(tool_name)
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "query": arguments["query"],
                            "required_tags": [],
                            "forbidden_tags": [],
                            "resolved_query": arguments["query"],
                            "limit": arguments["limit"],
                            "offset": arguments["offset"],
                            "total_matches": 1,
                            "returned_count": 1,
                            "results": [
                                {
                                    "note_id": "n1",
                                    "preview_text": "social security number",
                                    "content_text": "social security number",
                                    "context_text": "social security number",
                                    "tag_terms": ["security"],
                                    "effective_tag_terms": ["security"],
                                }
                            ],
                        },
                    }
                }
            }
        raise AssertionError(f"Unexpected tool call: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_rewrite_request(
        user_message="What is my social security number?",
        search_context_query="",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=6,
        max_expressions=20,
        hydrate_top_k=10,
        regex_engine="python-re",
        progress_callback=None,
    )

    assert result["ok"] is True
    assert len(expression_tool_order) >= 2
    assert expression_tool_order[0] == "search_notes_regex"


def test_run_rewrite_fails_fast_on_synthesis_access_refusal_with_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    model_calls = iter(
        [
            (
                {
                    "reasoning": "Value regex only.",
                    "expressions": [
                        {"type": "regex", "pattern": "[0-9]{3}-[0-9]{2}-[0-9]{4}", "flags": "ims"},
                    ],
                },
                '{"reasoning":"Value regex only.","expressions":[{"type":"regex","pattern":"[0-9]{3}-[0-9]{2}-[0-9]{4}","flags":"ims"}]}',
            ),
            (
                {
                    "reasoning": "Need final synthesis for best answer wording.",
                    "decision": "continue",
                    "answer": "",
                    "clarifying_question": "",
                    "confidence": "medium",
                    "continue_reason": "Run synthesis pass.",
                },
                '{"reasoning":"Need final synthesis for best answer wording.","decision":"continue","answer":"","clarifying_question":"","confidence":"medium","continue_reason":"Run synthesis pass."}',
            ),
            (
                {"answer": "I do not have access to your personal information."},
                '{"answer":"I do not have access to your personal information."}',
            ),
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: next(model_calls),
    )

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name == "count_notes":
            return {"result": {"structuredContent": {"ok": True, "data": {"total_notes": 100}}}}
        if tool_name == "search_notes_regex":
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "pattern": arguments["pattern"],
                            "flags": arguments["flags"],
                            "regex_engine": arguments["regex_engine"],
                            "target": arguments["target"],
                            "scope_count": len(arguments.get("scope_note_ids", [])),
                            "limit": arguments["limit"],
                            "offset": arguments["offset"],
                            "total_matches": 1,
                            "returned_count": 1,
                            "results": [
                                {
                                    "note_id": "n1",
                                    "preview_text": "SSN: 123-45-6789",
                                    "content_text": "SSN: 123-45-6789",
                                    "context_text": "ME --- SSN: 123-45-6789",
                                    "tag_terms": ["ssn"],
                                    "effective_tag_terms": ["ssn"],
                                    "matches": [
                                        {
                                            "field": "context_text",
                                            "start": 0,
                                            "end": 11,
                                            "snippet": "SSN: 123-45-6789",
                                            "normalized_text_match": False,
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                }
            }
        raise AssertionError(f"Unexpected tool call: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_rewrite_request(
        user_message="What is my social security number?",
        search_context_query="",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=6,
        max_expressions=20,
        hydrate_top_k=10,
        regex_engine="python-re",
        progress_callback=None,
    )

    assert result["ok"] is False
    assert "Synthesis failed" in result["answer"]
    assert any(step.get("action") == "synthesis_error" for step in result["steps"])


def test_run_rewrite_returns_no_evidence_without_synthesis(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    model_calls = iter(
        [
            (
                {
                    "reasoning": "Simple plan",
                    "expressions": [{"type": "phrase", "value": "mom birthday"}],
                },
                '{"reasoning":"Simple plan","expressions":[{"type":"phrase","value":"mom birthday"}]}',
            ),
            (
                {
                    "reasoning": "No hits yet, continue if more expressions exist.",
                    "decision": "continue",
                    "answer": "",
                    "clarifying_question": "",
                    "confidence": "low",
                    "continue_reason": "No evidence yet.",
                },
                '{"reasoning":"No hits yet, continue if more expressions exist.","decision":"continue","answer":"","clarifying_question":"","confidence":"low","continue_reason":"No evidence yet."}',
            ),
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: next(model_calls),
    )

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name == "count_notes":
            return {"result": {"structuredContent": {"ok": True, "data": {"total_notes": 100}}}}
        if tool_name == "search_notes":
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "query": arguments["query"],
                            "required_tags": [],
                            "forbidden_tags": [],
                            "resolved_query": arguments["query"],
                            "limit": arguments["limit"],
                            "offset": arguments["offset"],
                            "total_matches": 0,
                            "returned_count": 0,
                            "results": [],
                        },
                    }
                }
            }
        raise AssertionError(f"Unexpected tool call: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_rewrite_request(
        user_message="When is my mom's birthday?",
        search_context_query="",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=6,
        max_expressions=20,
        hydrate_top_k=10,
        regex_engine="python-re",
        progress_callback=None,
    )

    assert result["ok"] is True
    assert "No matching evidence found" in result["answer"]
    assert any(step.get("action") == "no_evidence" for step in result["steps"])


def test_run_rewrite_skips_duplicate_compiled_queries_and_tracks_history(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "ensure_ollama_model_available",
        lambda *, ollama_chat_url, model, autopull: "qwen2.5:7b-instruct",
    )

    near_pattern = mcp_client._compile_near_regex_pattern(
        left="123",
        right="456",
        window_chars=200,
    )
    model_calls = iter(
        [
            (
                {
                    "reasoning": "Use one proximity expression and an equivalent regex.",
                    "expressions": [
                        {
                            "type": "near",
                            "left": "123",
                            "right": "456",
                            "window_chars": 200,
                        },
                        {
                            "type": "regex",
                            "pattern": near_pattern,
                            "flags": "is",
                        },
                    ],
                },
                '{"reasoning":"Use one proximity expression and an equivalent regex.","expressions":[{"type":"near","left":"123","right":"456","window_chars":200},{"type":"regex","pattern":"'
                + near_pattern.replace("\\", "\\\\").replace('"', '\\"')
                + '","flags":"is"}]}',
            ),
            (
                {
                    "reasoning": "No evidence yet; continue.",
                    "decision": "continue",
                    "answer": "",
                    "clarifying_question": "",
                    "confidence": "low",
                    "continue_reason": "Run remaining expressions.",
                },
                '{"reasoning":"No evidence yet; continue.","decision":"continue","answer":"","clarifying_question":"","confidence":"low","continue_reason":"Run remaining expressions."}',
            ),
        ]
    )
    monkeypatch.setattr(
        mcp_client,
        "_ollama_chat_json_with_raw",
        lambda *, ollama_chat_url, model, messages: next(model_calls),
    )

    regex_calls = []

    def fake_tools_call(*, url, request_id, tool_name, arguments):
        if tool_name == "count_notes":
            return {"result": {"structuredContent": {"ok": True, "data": {"total_notes": 100}}}}
        if tool_name == "search_notes_regex":
            regex_calls.append(dict(arguments))
            return {
                "result": {
                    "structuredContent": {
                        "ok": True,
                        "data": {
                            "pattern": arguments["pattern"],
                            "flags": arguments["flags"],
                            "regex_engine": arguments["regex_engine"],
                            "target": arguments["target"],
                            "scope_count": len(arguments.get("scope_note_ids", [])),
                            "limit": arguments["limit"],
                            "offset": arguments["offset"],
                            "total_matches": 0,
                            "returned_count": 0,
                            "results": [],
                        },
                    }
                }
            }
        raise AssertionError(f"Unexpected tool call: {tool_name}")

    monkeypatch.setattr(mcp_client, "_tools_call", fake_tools_call)

    result = mcp_client._run_rewrite_request(
        user_message="Where are 123 and 456 near each other?",
        search_context_query="",
        mcp_url="http://127.0.0.1:8000/api2/mcp",
        ollama_chat_url="http://127.0.0.1:11434/api/chat",
        model="qwen2.5:7b-instruct",
        max_steps=6,
        max_expressions=20,
        hydrate_top_k=10,
        regex_engine="python-re",
        progress_callback=None,
    )

    assert result["ok"] is True
    assert "No matching evidence found" in result["answer"]
    assert len(regex_calls) == 1
    assert any(
        step.get("action") == "expression_execute_skip_duplicate_query"
        for step in result["steps"]
    )

    reasoning_steps = [
        step for step in result["steps"] if step.get("action") == "iteration_reasoning"
    ]
    assert len(reasoning_steps) == 1
    messages = reasoning_steps[0]["model_payload"]["messages"]
    assert isinstance(messages, list)
    assert len(messages) >= 2
    user_payload = json.loads(messages[1]["content"])
    assert "already_executed_queries" in user_payload
    assert isinstance(user_payload["already_executed_queries"], list)
    assert len(user_payload["already_executed_queries"]) == 1


def test_extract_synthesis_answer_supports_nested_payloads() -> None:
    payload = {
        "result": {
            "metadata": {"foo": "bar"},
            "response": {
                "answer": "January 16",
            },
        }
    }
    assert mcp_client._extract_synthesis_answer(payload=payload) == "January 16"


def test_build_rewrite_synthesis_messages_blocks_access_disclaimer_pattern() -> None:
    messages = mcp_client._build_rewrite_synthesis_messages(
        user_message="What is my social security number?",
        search_context_query="",
        expression_plan={
            "reasoning": "test",
            "expressions": [{"type": "phrase", "value": "ssn"}],
        },
        expression_stats=[],
        hydrated_notes=[
            {
                "note_id": "n1",
                "hit_count": 1,
                "matched_expressions": ['phrase:"ssn"'],
                "content_excerpt": "ssn: 123-45-6789",
                "context_excerpt": "ssn: 123-45-6789",
                "term_snippets": ["ssn: 123-45-6789"],
            }
        ],
    )

    assert len(messages) == 3
    system_message = messages[0]
    assert system_message["role"] == "system"
    content = system_message["content"]
    assert "do not refuse based on lack of access" in content
    assert "Never answer with capability disclaimers" in content


def test_rank_candidate_note_ids_prefers_specific_expression_matches() -> None:
    ordered, metadata = mcp_client._rank_candidate_note_ids(
        note_hit_counts={
            "broad-note": 1,
            "specific-note": 1,
        },
        note_hit_expressions={
            "broad-note": ['phrase:"sin"'],
            "specific-note": ['phrase:"social security number"'],
        },
        expression_stats=[
            {
                "expression_label": 'phrase:"sin"',
                "expression": {"type": "phrase", "value": "sin"},
                "scoped_match_count": 4000,
            },
            {
                "expression_label": 'phrase:"social security number"',
                "expression": {"type": "phrase", "value": "social security number"},
                "scoped_match_count": 4,
            },
        ],
        universe_note_count=100000,
        universe_note_ids=None,
    )
    assert ordered[0] == "specific-note"
    assert isinstance(metadata, dict)
    assert "expression_weights" in metadata
