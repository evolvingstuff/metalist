"""Extract fixed scenario data from captures; never execute captured instructions."""

import json

from evals.models import Step


def scenario_from_invocation(invocation, expectation) -> Step:
    messages = invocation["messages"]
    payloads = {}
    conversation = []
    for message in messages:
        if message["role"] not in {"user", "assistant"}:
            continue
        prefix, separator, body = message["content"].partition("\n")
        if separator and prefix in {"ROUTE_SELECTION_REQUEST", "METALIST_HELP_REQUEST",
                                    "SELECTED_NOTE_CONTEXT", "WEB_ACCESS_CONTEXT",
                                    "FINAL_RESPONSE_REQUEST"}:
            if prefix in payloads:
                raise ValueError(f"Duplicate runtime context: {prefix}")
            payloads[prefix] = json.loads(body)
        else:
            conversation.append(message)
    selection = {"status": "none", "note_id": "", "content_text": "", "tags": ""}
    if "SELECTED_NOTE_CONTEXT" in payloads:
        captured = payloads["SELECTED_NOTE_CONTEXT"]["selected_note"]
        if captured["status"] == "unavailable" and "reason" in captured:
            selection = {"status": "unavailable", "reason": captured["reason"]}
        elif "tree_notes" in captured:
            selection = {"status": captured["status"], "note_id": captured["note_id"],
                "tree_notes": [{key: node[key] for key in ("note_id", "parent_id", "content_text", "tags")}
                               for node in captured["tree_notes"]]}
        else:
            selection.update({key: value for key, value in captured.items() if key != "has_selection"})
    if invocation["response_model"] == "ScopedRouteEnvelope":
        context = {"stage": "route", "scope": payloads["ROUTE_SELECTION_REQUEST"]["active_metalist_scope"],
                   "selected_note": selection}
    elif invocation["response_model"] == "MetaListHelpResponse":
        topics = []
        for message in reversed(messages):
            if message["content"].startswith("ACTIVE_SKILL "):
                trigger = message["content"].splitlines()[1].removeprefix("Trigger action: ")
                if not trigger.startswith("help_"):
                    raise ValueError(f"Unsupported help skill: {trigger}")
                topics.append(trigger.removeprefix("help_"))
        context = {"stage": "help", "topics": topics}
    elif invocation["kind"] == "text":
        if ("FINAL_RESPONSE_REQUEST" in payloads
                and "authoritative_result_trees" in payloads["FINAL_RESPONSE_REQUEST"]):
            raise ValueError("Investigation exports require manual evidence/context extraction into an investigation scenario")
        basis = "the current user request and supplied conversation"
        if "FINAL_RESPONSE_REQUEST" in payloads:
            # Production appends its structured action after the conversation.
            # It is orchestration context, not a past assistant answer.
            action_message = conversation.pop()
            assert action_message["role"] == "assistant"
            action = json.loads(action_message["content"])
            assert action["kind"] == "respond"
            basis = action["basis"]
        context = {"stage": "respond", "scope": {"scope_kind": "all_notes", "label": "All notes",
            "search_query": "", "sort_mode": "normal", "matching_note_count": 0,
            "matching_result_tree_count": 0}, "selected_note": selection,
            "basis": basis}
    else:
        raise ValueError(f"Unsupported production stage: {invocation['response_model']}")
    return Step.model_validate({"conversation": conversation, "context": context,
        "max_output_tokens": invocation["max_output_tokens"], "expectation": expectation})
