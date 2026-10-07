"""The agent's own record of what it did for an answer.

Each tool call becomes one short entry: what was asked and what came of it,
never the content a tool returned (page text and notes can be huge, and the
model can read them again). The entries are kept with the answer for the rest of
the chat and given to the model on later turns, so a question such as "did you
search the web for that?" is answered from what actually happened. Only the
model sees them.
"""

from __future__ import annotations

import json


_NOTE_READ_TOOLS = frozenset({"read_view_notes", "search_view_notes"})
_OPERATION_TOOLS = frozenset({"summarize_view", "propose_tag_generation", "propose_tag_review"})
_KNOWN_TOOLS = _NOTE_READ_TOOLS | _OPERATION_TOOLS | {
    "lookup_metalist_help", "view_overview", "open_web_pages", "open_menu",
}


def describe_action(*, name: str, arguments: str, result_content: str, is_error: bool) -> dict[str, object]:
    """One log entry for a tool call, from its JSON arguments and JSON result."""
    # A rejected call may name a tool that does not exist: it is still recorded.
    if is_error:
        return {"tool": name, "rejected": True}
    if name not in _KNOWN_TOOLS:
        raise ValueError(f"No action log entry for unknown tool: {name!r}")
    parsed_arguments = json.loads(arguments)
    assert isinstance(parsed_arguments, dict), "Tool arguments are a JSON object"
    if name in _OPERATION_TOOLS:
        return {"tool": name, "arguments": parsed_arguments}
    result = json.loads(result_content)
    assert isinstance(result, dict), "Tool results are a JSON object"
    if name == "lookup_metalist_help":
        return {"tool": name, "topics": list(parsed_arguments["topics"])}
    if name == "view_overview":
        return {"tool": name, "notes_in_view": result["note_count"], "trees_in_view": result["tree_count"]}
    if name == "open_menu":
        return {"tool": name, "menu": result["label"], "status": result["status"]}
    if name == "open_web_pages":
        return {"tool": name, "pages": [_page_entry(page) for page in result["pages"]]}
    entry: dict[str, object] = {"tool": name}
    if name == "search_view_notes":
        entry["query"] = parsed_arguments["query"]
        entry["matching_notes"] = result["matching_note_count"]
    entry["trees_read"] = len(result["trees"])
    entry["trees_left_unread"] = len(result["unread_root_ids"])
    entry["trees_too_large"] = len(result["too_large_root_ids"])
    return entry


def _page_entry(page: dict[str, object]) -> dict[str, object]:
    """The address as asked, whether it opened, and its title when it did."""
    title = ""
    if page["status"] == "ok":
        title = page["title"]
    return {"url": page["requested_url"], "status": page["status"], "title": title}
