from __future__ import annotations

import app.api.routes.ontology as ontology_route


def test_empty_catalog_query_returns_total_without_materializing_every_tag(monkeypatch) -> None:
    monkeypatch.setattr(ontology_route, "get_ontology", lambda: object())
    monkeypatch.setattr(
        ontology_route.search_index,
        "list_tag_frequencies",
        lambda: {"journal": 8, "project": 3},
    )
    monkeypatch.setattr(
        ontology_route,
        "extract_ontology_tags",
        lambda _ontology: {"journal", "project", "ontology-only"},
    )

    payload = ontology_route.list_tags(q="", limit=0)

    assert payload == {"totalCount": 3, "tags": []}


def test_catalog_query_honors_a_positive_result_limit(monkeypatch) -> None:
    monkeypatch.setattr(ontology_route, "get_ontology", lambda: object())
    monkeypatch.setattr(
        ontology_route.search_index,
        "list_tag_frequencies",
        lambda: {"journal": 8, "project": 3},
    )
    monkeypatch.setattr(
        ontology_route,
        "extract_ontology_tags",
        lambda _ontology: {"journal", "project", "ontology-only"},
    )

    payload = ontology_route.list_tags(q="", limit=2)

    assert payload == {
        "totalCount": 3,
        "tags": [
            {"tag": "journal", "count": 8},
            {"tag": "project", "count": 3},
        ],
    }
