from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.search_index import search_index
from app.services.ontology_rules_store import (
    build_direct_edge_rule_map,
    create_rule_line,
    delete_rule_line,
    extract_ontology_tags,
    get_ontology,
    list_rule_lines,
    update_rule_line,
)


router = APIRouter(prefix="/ontology", tags=["ontology2"])


@router.get("/rules")
def list_rules() -> dict:
    rules = [{"id": rule_id, "text": text} for rule_id, text in list_rule_lines()]
    return {"rules": rules}


@router.post("/rules")
def create_rule(payload: dict) -> dict:
    text = payload["text"]
    if not isinstance(text, str):
        raise HTTPException(status_code=400, detail="text must be a string")
    if text.strip() == "":
        raise HTTPException(status_code=400, detail="text must be non-empty")
    rule_id, normalized = create_rule_line(text=text)
    return {"id": rule_id, "text": normalized}


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, payload: dict) -> dict:
    text = payload["text"]
    if not isinstance(text, str):
        raise HTTPException(status_code=400, detail="text must be a string")
    if text.strip() == "":
        raise HTTPException(status_code=400, detail="text must be non-empty")

    existing = list_rule_lines()
    if rule_id < 0 or rule_id >= len(existing):
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")

    updated_id, normalized = update_rule_line(rule_id=rule_id, text=text)
    return {"id": updated_id, "text": normalized}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int) -> dict:
    existing = list_rule_lines()
    if rule_id < 0 or rule_id >= len(existing):
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")

    delete_rule_line(rule_id=rule_id)
    return {"ok": True}


@router.get("/focus")
def focus_view(tag: str) -> dict:
    ontology = get_ontology()
    left, middle, right = ontology.focus_view(tag=tag)

    edge_map = build_direct_edge_rule_map()
    direct_left: list[dict] = []
    direct_right: list[dict] = []
    direct_middle: list[dict] = []

    equals = set(middle)

    for candidate in sorted(left):
        if candidate in equals:
            continue
        key = (candidate, tag)
        if key in edge_map:
            direct_left.append({"tag": candidate, "ruleId": edge_map[key]})

    for candidate in sorted(right):
        if candidate in equals:
            continue
        key = (tag, candidate)
        if key in edge_map:
            direct_right.append({"tag": candidate, "ruleId": edge_map[key]})

    for candidate in sorted(equals):
        if candidate == tag:
            continue
        forward_key = (tag, candidate)
        backward_key = (candidate, tag)
        if forward_key not in edge_map or backward_key not in edge_map:
            continue
        forward = edge_map[forward_key]
        backward = edge_map[backward_key]
        if forward != backward:
            continue
        direct_middle.append({"tag": candidate, "ruleId": forward})

    indirect_left = sorted([t for t in left if t not in equals and (t, tag) not in edge_map])
    indirect_right = sorted([t for t in right if t not in equals and (tag, t) not in edge_map])
    indirect_middle = sorted([t for t in equals if t != tag and t not in {row["tag"] for row in direct_middle}])

    return {
        "focusTag": tag,
        "leftDirect": direct_left,
        "leftIndirect": indirect_left,
        "middle": sorted(equals),
        "middleDirect": direct_middle,
        "middleIndirect": indirect_middle,
        "rightDirect": direct_right,
        "rightIndirect": indirect_right,
    }


@router.get("/tags")
def list_tags(q: str, limit: int) -> dict:
    if not isinstance(limit, int):
        raise TypeError("limit must be an int")
    if limit < 0:
        raise ValueError("limit must be >= 0")

    ontology = get_ontology()
    tags = set(search_index.list_non_meta_tag_terms())
    tags.update(extract_ontology_tags(ontology))

    needle = q.casefold()
    matches: list[str] = []
    for tag in sorted(tags):
        if needle and needle not in tag.casefold():
            continue
        matches.append(tag)
        if len(matches) >= limit:
            break

    return {"totalCount": len(tags), "tags": matches}
