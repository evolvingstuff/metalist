from types import SimpleNamespace

from app.services.ai_chat_rendering import render_ai_chat_markdown_to_html
from app.services.ai_chat_rendering import sanitize_ai_chat_markdown_citations


NOTE_ID = "75193dae-9e05-4a4e-94bf-417ffde18957"
SECOND_NOTE_ID = "75ee44d0-7aee-49a4-935a-a059b02c4bb4"
ROOT_NOTE_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ROOT_NOTE_ID = "22222222-2222-4222-8222-222222222222"
MISSING_ID = "99999999-9999-4999-9999-999999999999"


class FakeNotes:
    def has_note(self, note_id: str) -> bool:
        return note_id in {
            ROOT_NOTE_ID,
            OTHER_ROOT_NOTE_ID,
            NOTE_ID,
            SECOND_NOTE_ID,
        }

    def get_note(self, note_id: str):
        if note_id == ROOT_NOTE_ID:
            return SimpleNamespace(
                id=ROOT_NOTE_ID,
                parent_id=None,
                content="<h1>Incorporate AI</h1>",
                tags="architecture",
            )
        if note_id == OTHER_ROOT_NOTE_ID:
            return SimpleNamespace(
                id=OTHER_ROOT_NOTE_ID,
                parent_id=None,
                content="<h1>Other architecture decision</h1>",
                tags="architecture",
            )
        if note_id == NOTE_ID:
            return SimpleNamespace(
                id=NOTE_ID,
                parent_id=ROOT_NOTE_ID,
                content="<h1>Instructor + LiteLLM vs. Pydantic AI</h1><p>Details</p>",
                tags="architecture",
            )
        assert note_id == SECOND_NOTE_ID
        return SimpleNamespace(
            id=SECOND_NOTE_ID,
            parent_id=ROOT_NOTE_ID,
            content="<h1>Pydantic AI might be useful later</h1>",
            tags="architecture",
        )


def test_ai_chat_renderer_moves_bare_note_uuid_to_references_section() -> None:
    rendered = render_ai_chat_markdown_to_html(
        f"See note {NOTE_ID} for details.",
        notes=FakeNotes(),
        allowed_note_ids=(NOTE_ID,),
    )

    assert f">{NOTE_ID}<" not in rendered
    assert (
        '<span class="ai-chat-note-mention">'
        "“Instructor + LiteLLM vs. Pydantic AI”</span>"
    ) in rendered
    body_html, references_html = rendered.split('<section class="ai-chat-references"')
    assert 'class="note-reference-link"' not in body_html
    assert 'aria-label="References"' in references_html
    assert 'class="ai-chat-note-reference note-reference-block' in rendered
    assert f'data-ref-note-id="{ROOT_NOTE_ID}"' in rendered
    assert 'class="note-reference-link"' in rendered
    assert "Incorporate AI" in references_html


def test_ai_chat_renderer_mentions_explicit_reference_without_leaving_brackets() -> None:
    rendered = render_ai_chat_markdown_to_html(
        f"Source: [[{NOTE_ID}]]",
        notes=FakeNotes(),
        allowed_note_ids=(NOTE_ID,),
    )

    assert "[[" not in rendered
    assert "]]" not in rendered
    assert '<sup class="ai-chat-citation-marker"' in rendered
    assert 'class="ai-chat-citation-link note-reference-link"' in rendered
    assert f'data-ref-note-id="{ROOT_NOTE_ID}"' in rendered
    assert ">[1]</a></sup>" in rendered
    assert f'data-ref-query="{NOTE_ID}"' in rendered
    assert rendered.count('class="note-reference-link"') == 1


def test_ai_chat_renderer_hides_partial_bracketed_citation_during_streaming() -> None:
    rendered = render_ai_chat_markdown_to_html(
        f"Supported finding. [[{NOTE_ID}]",
        notes=FakeNotes(),
        allowed_note_ids=(NOTE_ID,),
    )

    assert "Supported finding." in rendered
    assert NOTE_ID not in rendered
    assert "Instructor + LiteLLM" not in rendered
    assert 'class="ai-chat-note-mention"' not in rendered
    assert 'class="ai-chat-citation-marker"' not in rendered
    assert 'class="ai-chat-references"' not in rendered


def test_ai_chat_renderer_deduplicates_repeated_reference_links() -> None:
    rendered = render_ai_chat_markdown_to_html(
        f"Compare [[{NOTE_ID}]] with {NOTE_ID}.",
        notes=FakeNotes(),
        allowed_note_ids=(NOTE_ID,),
    )

    assert rendered.count('class="ai-chat-note-mention"') == 1
    assert rendered.count('class="ai-chat-citation-marker"') == 1
    assert rendered.count('class="note-reference-link"') == 1
    assert 'class="ai-chat-open-all-references"' not in rendered


def test_ai_chat_renderer_adds_open_all_link_with_or_query_for_multiple_refs() -> None:
    rendered = render_ai_chat_markdown_to_html(
        f"Compare [[{NOTE_ID}]] and [[{OTHER_ROOT_NOTE_ID}]].",
        notes=FakeNotes(),
        allowed_note_ids=(NOTE_ID, OTHER_ROOT_NOTE_ID),
    )

    expected_query = f"{NOTE_ID} OR {OTHER_ROOT_NOTE_ID}"
    assert rendered.count('class="note-reference-link"') == 2
    assert 'class="ai-chat-open-all-references"' in rendered
    assert f'data-ref-query="{expected_query}"' in rendered
    assert ">Open all references</a>" in rendered


def test_ai_chat_renderer_groups_child_citations_into_one_root_reference() -> None:
    rendered = render_ai_chat_markdown_to_html(
        f"Compare [[{NOTE_ID}]] and [[{SECOND_NOTE_ID}]].",
        notes=FakeNotes(),
        allowed_note_ids=(NOTE_ID, SECOND_NOTE_ID),
    )

    assert 'class="ai-chat-note-mention"' not in rendered
    assert rendered.count('class="ai-chat-citation-marker"') == 2
    assert rendered.count('class="note-reference-link"') == 1
    assert rendered.count(">[1]</a></sup>") == 2
    assert f'data-ref-note-id="{ROOT_NOTE_ID}"' in rendered
    expected_query = f"{NOTE_ID} OR {SECOND_NOTE_ID}"
    assert f'data-ref-query="{expected_query}"' in rendered
    assert 'class="ai-chat-open-all-references"' not in rendered


def test_ai_chat_renderer_recovers_known_uuid_from_inline_code_and_unicode_dashes() -> None:
    for dash_character in "-‐‑‒–—−":
        unicode_dash_note_id = SECOND_NOTE_ID.replace("-", dash_character)
        rendered = render_ai_chat_markdown_to_html(
            f"The note with the ID `{unicode_dash_note_id}` discusses Pydantic AI.",
            notes=FakeNotes(),
            allowed_note_ids=(SECOND_NOTE_ID,),
        )

        assert f">{unicode_dash_note_id}<" not in rendered
        assert "Pydantic AI might be useful later" in rendered
        assert rendered.count('class="ai-chat-note-mention"') == 1
        assert rendered.count('class="note-reference-link"') == 1
        assert f'data-ref-note-id="{ROOT_NOTE_ID}"' in rendered


def test_ai_chat_renderer_suppresses_unknown_citations_but_preserves_fenced_code() -> None:
    rendered = render_ai_chat_markdown_to_html(
        f"Unknown {MISSING_ID}.\n\n```text\n{NOTE_ID}\n```",
        notes=FakeNotes(),
        allowed_note_ids=(),
    )

    assert MISSING_ID not in rendered
    assert NOTE_ID in rendered
    assert "<pre>" in rendered
    assert 'class="note-reference-link"' not in rendered
    assert 'class="ai-chat-references"' not in rendered


def test_ai_chat_sanitizer_removes_hallucinated_uuid_citations() -> None:
    sanitized = sanitize_ai_chat_markdown_citations(
        f"A grounded sentence. [[{MISSING_ID}]]",
        notes=FakeNotes(),
        allowed_note_ids=(NOTE_ID,),
    )

    assert sanitized == "A grounded sentence."


def test_ai_chat_renderer_suppresses_note_citations_not_retrieved_in_current_run() -> None:
    rendered = render_ai_chat_markdown_to_html(
        f"Bayes' theorem needs no saved notes. [[{NOTE_ID}]] `{SECOND_NOTE_ID}`",
        notes=FakeNotes(),
        allowed_note_ids=(),
    )

    assert "Bayes' theorem needs no saved notes." in rendered
    assert NOTE_ID not in rendered
    assert SECOND_NOTE_ID not in rendered
    assert "Instructor + LiteLLM" not in rendered
    assert "Pydantic AI" not in rendered
    assert 'class="ai-chat-note-mention"' not in rendered
    assert 'class="ai-chat-references"' not in rendered


def test_ai_chat_renderer_maps_numbered_citations_to_superscript_references() -> None:
    rendered = render_ai_chat_markdown_to_html(
        "First supported claim[citation:1] and second supported claim[citation:2].",
        notes=FakeNotes(),
        allowed_note_ids=(ROOT_NOTE_ID, OTHER_ROOT_NOTE_ID),
    )

    assert rendered.count('class="ai-chat-citation-marker"') == 2
    assert ">[1]</a></sup>" in rendered
    assert ">[2]</a></sup>" in rendered
    assert rendered.count('class="ai-chat-reference-number"') == 2
    assert rendered.count('class="note-reference-link"') == 2


def test_ai_chat_renderer_keeps_loose_cited_items_in_one_ordered_list() -> None:
    rendered = render_ai_chat_markdown_to_html(
        (
            "1. **Launch Date:** March 17, 2042.\n"
            "   [citation:1]\n\n"
            "2. **Launch Color:** Ultraviolet.\n"
            "   [citation:2]"
        ),
        notes=FakeNotes(),
        allowed_note_ids=(ROOT_NOTE_ID, OTHER_ROOT_NOTE_ID),
    )

    body_html, references_html = rendered.split('<section class="ai-chat-references"')
    assert body_html.count("<ol>") == 1
    assert body_html.count("<li>") == 2
    assert body_html.count('class="ai-chat-citation-marker"') == 2
    assert references_html.count('class="ai-chat-reference-number"') == 2


def test_ai_chat_sanitizer_canonicalizes_authorized_numbered_citations() -> None:
    sanitized = sanitize_ai_chat_markdown_citations(
        "First supported claim[citation:1].",
        notes=FakeNotes(),
        allowed_note_ids=(ROOT_NOTE_ID,),
    )

    assert sanitized == f"First supported claim[[{ROOT_NOTE_ID}]]."


def test_ai_chat_renderer_removes_standalone_source_lines_and_repairs_numbering() -> None:
    markdown = (
        "1. **Exercise:** Farmer's walks strengthen the core.\n\n"
        f"- **Source:** [YouTube Video](https://example.com/one) [[{NOTE_ID}]]\n\n"
        "1. **Exercise snacks:** Short workouts support muscle mass.\n\n"
        f"- **Source:** [YouTube Video](https://example.com/two) [[{SECOND_NOTE_ID}]]"
    )

    sanitized = sanitize_ai_chat_markdown_citations(
        markdown,
        notes=FakeNotes(),
        allowed_note_ids=(NOTE_ID, SECOND_NOTE_ID),
    )
    rendered = render_ai_chat_markdown_to_html(
        sanitized,
        notes=FakeNotes(),
        allowed_note_ids=(NOTE_ID, SECOND_NOTE_ID),
    )

    assert "Source:" not in sanitized
    assert "YouTube Video" not in sanitized
    assert "example.com" not in sanitized
    assert f"walks strengthen the core. [[{NOTE_ID}]]" in sanitized
    assert f"workouts support muscle mass. [[{SECOND_NOTE_ID}]]" in sanitized
    body_html, _references_html = rendered.split('<section class="ai-chat-references"')
    assert "YouTube Video" not in body_html
    assert "example.com" not in body_html
    assert body_html.count('<sup class="ai-chat-citation-marker"') == 2
    assert body_html.count("<ol>") == 1
    assert body_html.count("<li>") == 2
