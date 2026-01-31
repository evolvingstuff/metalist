from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.services.search_index import search_index
from app.services.note_store import store as note_store
from app.services.sync import generate_new_uuid
from app.services.view_cache import view_cache
from app.services.tag_ontology import RegexAtom, TagAtom, TextAtom, parse_rules_text
from app.services.ontology_rules_store import (
    build_direct_edge_rule_map,
    create_rule_line,
    delete_rule_line,
    extract_ontology_tags,
    get_ontology,
    list_rule_lines,
    update_rule_line,
)
from app.usecases.rename_tag import apply_rename_tag_everywhere


def _maybe_bearer_token(request: Request) -> str:
    if "authorization" not in request.headers:
        return ""
    authorization = request.headers["authorization"]
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    return parts[1]


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
    if note_store.loaded:
        note_store.rebuild_search_index_tag_terms()
        view_cache.clear()
        update_uuid = generate_new_uuid()
        return {"id": rule_id, "text": normalized, "updateUUID": update_uuid}
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
    if note_store.loaded:
        note_store.rebuild_search_index_tag_terms()
        view_cache.clear()
        update_uuid = generate_new_uuid()
        return {"id": updated_id, "text": normalized, "updateUUID": update_uuid}
    return {"id": updated_id, "text": normalized}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int) -> dict:
    existing = list_rule_lines()
    if rule_id < 0 or rule_id >= len(existing):
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")

    delete_rule_line(rule_id=rule_id)
    if note_store.loaded:
        note_store.rebuild_search_index_tag_terms()
        view_cache.clear()
        update_uuid = generate_new_uuid()
        return {"ok": True, "updateUUID": update_uuid}
    return {"ok": True}


@router.post("/rename-tag")
def rename_tag(request: Request, payload: dict) -> dict:
    old = payload["old"]
    new = payload["new"]
    if not isinstance(old, str) or old.strip() == "":
        raise HTTPException(status_code=400, detail="old must be a non-empty string")
    if not isinstance(new, str) or new.strip() == "":
        raise HTTPException(status_code=400, detail="new must be a non-empty string")
    if old.strip() == new.strip():
        raise HTTPException(status_code=400, detail="old and new must differ")

    token = _maybe_bearer_token(request)
    return apply_rename_tag_everywhere(old=old, new=new, token=token)


@router.get("/focus")
def focus_view(tag: str) -> dict:
    ontology = get_ontology()
    left, middle, right = ontology.focus_view(tag=tag)

    edge_map = build_direct_edge_rule_map()
    direct_left: list[dict] = []
    direct_right: list[dict] = []
    direct_middle: list[dict] = []

    incoming_rules: list[dict] = []

    equals = set(middle)

    direct_left_tags: set[str] = set()
    direct_right_tags: set[str] = set()

    def format_atom(atom: object) -> tuple[str, str]:
        if isinstance(atom, TagAtom):
            return "tag", atom.tag
        if isinstance(atom, TextAtom):
            escaped = atom.phrase.replace("\\", "\\\\").replace('"', '\\"')
            return "text", f'"{escaped}"'
        if isinstance(atom, RegexAtom):
            return "regex", f"/{atom.pattern}/{atom.flags}"
        raise TypeError(f"Unknown atom: {type(atom)}")

    def atom_payload(atom: object) -> dict:
        kind, display = format_atom(atom)
        if kind == "tag":
            return {"kind": kind, "tag": display}
        if kind == "text":
            return {"kind": kind, "text": display}
        if kind == "regex":
            return {"kind": kind, "regex": display}
        raise RuntimeError(f"Unexpected atom kind: {kind}")

    def format_atom_for_edit(atom: object) -> str:
        if isinstance(atom, TagAtom):
            return atom.tag
        if isinstance(atom, TextAtom):
            escaped = atom.phrase.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        if isinstance(atom, RegexAtom):
            escaped = atom.pattern.replace("\\", "\\\\").replace("/", "\\/")
            return f"/{escaped}/{atom.flags}"
        raise TypeError(f"Unknown atom: {type(atom)}")

    for rule_id, text in list_rule_lines():
        # Avoid duplicating SCC/equality rows; the middle column handles synonyms.
        if "=>" not in text and "=" in text:
            continue

        rules = parse_rules_text(text=f"{text}\n", filename=f"ontology_rules.txt:{rule_id}")
        matched_rhs: str | None = None
        lhs_tag: str | None = None

        matched_rule = None
        for rule in rules:
            if rule.rhs not in equals:
                continue
            matched_rhs = rule.rhs
            matched_rule = rule
            if len(rule.lhs) == 1 and isinstance(rule.lhs[0], TagAtom):
                lhs_tag = rule.lhs[0].tag
            break
        if matched_rhs is None:
            continue

        if matched_rule is None:
            raise RuntimeError('Expected matched_rule to be set when matched_rhs is present')

        lhs_atoms_payload = [atom_payload(atom) for atom in matched_rule.lhs]

        if len(matched_rule.lhs) == 1:
            atom = matched_rule.lhs[0]
            kind, display = format_atom(atom)
            edit_value = format_atom_for_edit(atom)
        else:
            kind = 'and'
            display = ' '.join(format_atom(atom)[1] for atom in matched_rule.lhs)
            edit_value = ' '.join(format_atom_for_edit(atom) for atom in matched_rule.lhs)

        if lhs_tag is not None and lhs_tag not in equals:
            direct_left_tags.add(lhs_tag)

        incoming_rules.append(
            {
                "id": rule_id,
                "kind": kind,
                "display": display,
                "editValue": edit_value,
                "lhsAtoms": lhs_atoms_payload,
                "text": text,
                "rhs": matched_rhs,
                "lhsTag": lhs_tag,
            }
        )

    for candidate in sorted(left):
        if candidate in equals:
            continue
        rule_ids: set[int] = set()
        for member in equals:
            key = (candidate, member)
            if key in edge_map:
                rule_ids.add(edge_map[key])
        if not rule_ids:
            continue
        direct_left.append({"tag": candidate, "ruleIds": sorted(rule_ids)})

    for candidate in sorted(right):
        if candidate in equals:
            continue
        rule_ids: set[int] = set()
        for member in equals:
            key = (member, candidate)
            if key in edge_map:
                rule_ids.add(edge_map[key])
        if not rule_ids:
            continue
        direct_right_tags.add(candidate)
        direct_right.append({"tag": candidate, "ruleIds": sorted(rule_ids)})

    for candidate in sorted(equals):
        if candidate == tag:
            continue
        forward_key = (tag, candidate)
        backward_key = (candidate, tag)
        if forward_key not in edge_map or backward_key not in edge_map:
            continue
        forward = edge_map[forward_key]
        backward = edge_map[backward_key]
        direct_middle.append({"tag": candidate, "ruleIds": sorted({forward, backward})})

    indirect_left = sorted([t for t in left if t not in equals and t not in direct_left_tags])
    indirect_right = sorted([t for t in right if t not in equals and t not in direct_right_tags])
    indirect_middle = sorted([t for t in equals if t != tag and t not in {row["tag"] for row in direct_middle}])

    return {
        "focusTag": tag,
        "incomingRules": incoming_rules,
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
