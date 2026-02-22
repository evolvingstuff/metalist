from __future__ import annotations

import mcp_client


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
