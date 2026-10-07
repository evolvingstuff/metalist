"""The agent's own record of what it did for an answer (app/services/agent/action_log.py).

Kept for the chat so a later question such as "did you search the web?" is
answered from what actually happened; only the model sees it.
"""

from __future__ import annotations

import json

import pytest

from app.services.agent.action_log import describe_action


def _describe(name: str, arguments: dict[str, object], result: dict[str, object], is_error: bool) -> dict[str, object]:
    return describe_action(name=name, arguments=json.dumps(arguments), result_content=json.dumps(result),
                           is_error=is_error)


def test_help_lookup_records_its_topics() -> None:
    assert _describe("lookup_metalist_help", {"topics": ["ai", "search"]}, {"topics": []}, False) == {
        "tool": "lookup_metalist_help", "topics": ["ai", "search"]}


def test_note_reads_record_how_much_was_read() -> None:
    overview = {"note_count": 1600, "tree_count": 560, "trees": [{}, {}]}
    assert _describe("view_overview", {}, overview, False) == {
        "tool": "view_overview", "notes_in_view": 1600, "trees_in_view": 560}
    read = {"trees": [{}, {}, {}], "unread_root_ids": ["a", "b"], "too_large_root_ids": ["c"], "unknown_ids": []}
    assert _describe("read_view_notes", {"note_ids": []}, read, False) == {
        "tool": "read_view_notes", "trees_read": 3, "trees_left_unread": 2, "trees_too_large": 1}
    search = {"query": "ssm", "matching_note_count": 7, "matching_note_ids": [], "trees": [{}],
              "unread_root_ids": [], "too_large_root_ids": [], "unknown_ids": []}
    assert _describe("search_view_notes", {"query": "ssm"}, search, False) == {
        "tool": "search_view_notes", "query": "ssm", "matching_notes": 7, "trees_read": 1,
        "trees_left_unread": 0, "trees_too_large": 0}


def test_web_pages_record_each_address_status_and_title() -> None:
    result = {"pages": [
        {"requested_url": "https://www.google.com/search?q=ssm", "final_url": "https://www.google.com/search?q=ssm",
         "title": "Google Search", "content_text": "long page text", "status": "ok"},
        {"requested_url": "https://arxiv.org/abs/2405.21060", "final_url": "https://arxiv.org/abs/2405.21060",
         "title": "Transformers are SSMs", "content_text": "long", "status": "ok"},
        {"requested_url": "https://example.com/x", "final_url": "https://example.com/x", "status": "failed",
         "error_kind": "http_status"},
        {"requested_url": "https://blocked.example/", "status": "blocked",
         "error_kind": "not_available_in_permitted_context"},
    ]}
    described = _describe("open_web_pages", {"urls": []}, result, False)
    assert described == {"tool": "open_web_pages", "pages": [
        {"url": "https://www.google.com/search?q=ssm", "status": "ok", "title": "Google Search"},
        {"url": "https://arxiv.org/abs/2405.21060", "status": "ok", "title": "Transformers are SSMs"},
        {"url": "https://example.com/x", "status": "failed", "title": ""},
        {"url": "https://blocked.example/", "status": "blocked", "title": ""},
    ]}
    # Page text is never kept: only what was done and what came of it.
    assert "long" not in json.dumps(described)


def test_menus_and_operations_record_what_was_asked() -> None:
    assert _describe("open_menu", {"menu_id": "form.dictation_settings"},
                     {"menu_id": "form.dictation_settings", "label": "Dictation Settings", "status": "opened"},
                     False) == {"tool": "open_menu", "menu": "Dictation Settings", "status": "opened"}
    assert _describe("propose_tag_review", {"action": "accept", "scope": "current_view", "tag_filter": "ssm"},
                     {}, False) == {"tool": "propose_tag_review", "arguments": {
                         "action": "accept", "scope": "current_view", "tag_filter": "ssm"}}


def test_a_rejected_call_records_that_it_was_rejected() -> None:
    assert _describe("read_view_notes", {"note_ids": ["x"]}, {"error": "Unknown note"}, True) == {
        "tool": "read_view_notes", "rejected": True}


def test_an_unknown_tool_is_a_bug() -> None:
    with pytest.raises(ValueError):
        _describe("delete_everything", {}, {}, False)
