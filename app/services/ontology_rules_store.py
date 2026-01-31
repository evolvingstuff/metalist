from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import List, Mapping, Optional, Sequence, Tuple

from app.services.tag_ontology import TagAtom, TagOntology, compile_rules, parse_rules_text


def _ontology_rules_path() -> Path:
    return Path(__file__).resolve().parents[2] / "ontology_rules.txt"


def _is_comment_or_blank(line: str) -> bool:
    stripped = line.strip()
    if stripped == "":
        return True
    if stripped.startswith("#"):
        return True
    if stripped.startswith("//"):
        return True
    return False


def _replace_tag_tokens_in_line(*, line: str, old: str, new: str) -> str:
    if not isinstance(line, str):
        raise TypeError('line must be a string')
    if not isinstance(old, str) or old == '':
        raise TypeError('old must be a non-empty string')
    if not isinstance(new, str) or new == '':
        raise TypeError('new must be a non-empty string')

    if _is_comment_or_blank(line):
        return line

    out = ''
    i = 0
    in_quote: Optional[str] = None
    in_regex = False
    while i < len(line):
        ch = line[i]

        if in_quote is not None:
            out += ch
            if ch == '\\':
                if i + 1 < len(line):
                    out += line[i + 1]
                    i += 2
                    continue
            if ch == in_quote:
                in_quote = None
            i += 1
            continue

        if in_regex:
            out += ch
            if ch == '\\':
                if i + 1 < len(line):
                    out += line[i + 1]
                    i += 2
                    continue
            if ch == '/':
                in_regex = False
            i += 1
            continue

        if ch in ('\"', "'"):
            in_quote = ch
            out += ch
            i += 1
            continue

        if ch == '/':
            in_regex = True
            out += ch
            i += 1
            continue

        if ch.isspace() or ch in '()':
            out += ch
            i += 1
            continue

        start = i
        while i < len(line):
            nxt = line[i]
            if nxt.isspace() or nxt in '()':
                break
            if nxt in ('\"', "'", '/'):  # start of quoted phrase/regex
                break
            i += 1
        token = line[start:i]
        if token == old:
            out += new
        else:
            out += token

    return out


def _read_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return text.splitlines()


def _write_lines(path: Path, lines: Sequence[str]) -> None:
    payload = "\n".join(lines)
    if payload:
        payload += "\n"
    path.write_text(payload, encoding="utf-8")


def _compile_ontology(path: Path, lines: Sequence[str]) -> TagOntology:
    text = "\n".join(lines)
    if text:
        text += "\n"
    parsed = parse_rules_text(text=text, filename=str(path))
    return compile_rules(rules=parsed, filename=str(path))


def _file_mtime_ns(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    return path.stat().st_mtime_ns


@dataclass(frozen=True, slots=True)
class OntologyRulesState:
    path: Path
    mtime_ns: Optional[int]
    lines: Tuple[str, ...]
    rule_line_indexes: Tuple[int, ...]
    ontology: TagOntology


_LOCK = RLock()
_STATE: Optional[OntologyRulesState] = None


def _load_state_locked() -> OntologyRulesState:
    global _STATE

    path = _ontology_rules_path()
    current_mtime_ns = _file_mtime_ns(path)
    cached = _STATE
    if cached is not None and cached.path == path and cached.mtime_ns == current_mtime_ns:
        return cached

    lines = _read_lines(path)
    rule_line_indexes: List[int] = []
    for idx, line in enumerate(lines):
        if _is_comment_or_blank(line):
            continue
        rule_line_indexes.append(idx)

    ontology = _compile_ontology(path, lines)

    state = OntologyRulesState(
        path=path,
        mtime_ns=current_mtime_ns,
        lines=tuple(lines),
        rule_line_indexes=tuple(rule_line_indexes),
        ontology=ontology,
    )

    _STATE = state
    return state


def get_ontology() -> TagOntology:
    with _LOCK:
        return _load_state_locked().ontology


def list_rule_lines() -> List[Tuple[int, str]]:
    with _LOCK:
        state = _load_state_locked()
        out: List[Tuple[int, str]] = []
        for rule_id, file_index in enumerate(state.rule_line_indexes):
            text = state.lines[file_index].strip()
            out.append((rule_id, text))
        return out


def _require_rule_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("rule text must be a string")
    stripped = text.strip()
    if stripped == "":
        raise ValueError("rule text must be non-empty")
    if stripped.startswith("#") or stripped.startswith("//"):
        raise ValueError("rule text must not start with a comment marker")
    return stripped


def _update_rules_locked(*, new_lines: Sequence[str]) -> OntologyRulesState:
    global _STATE

    path = _ontology_rules_path()
    ontology = _compile_ontology(path, new_lines)
    _write_lines(path, new_lines)

    refreshed_lines = _read_lines(path)
    rule_line_indexes: List[int] = []
    for idx, line in enumerate(refreshed_lines):
        if _is_comment_or_blank(line):
            continue
        rule_line_indexes.append(idx)

    refreshed_state = OntologyRulesState(
        path=path,
        mtime_ns=_file_mtime_ns(path),
        lines=tuple(refreshed_lines),
        rule_line_indexes=tuple(rule_line_indexes),
        ontology=ontology,
    )

    _STATE = refreshed_state
    return refreshed_state


def create_rule_line(*, text: str) -> Tuple[int, str]:
    normalized = _require_rule_text(text)
    with _LOCK:
        state = _load_state_locked()
        lines = list(state.lines)
        lines.append(normalized)
        updated = _update_rules_locked(new_lines=lines)
        new_rule_id = len(updated.rule_line_indexes) - 1
        return new_rule_id, normalized


def update_rule_line(*, rule_id: int, text: str) -> Tuple[int, str]:
    if not isinstance(rule_id, int):
        raise TypeError("rule_id must be an int")
    if rule_id < 0:
        raise ValueError("rule_id must be >= 0")

    normalized = _require_rule_text(text)
    with _LOCK:
        state = _load_state_locked()
        if rule_id >= len(state.rule_line_indexes):
            raise IndexError(f"rule_id out of range: {rule_id}")
        file_index = state.rule_line_indexes[rule_id]

        lines = list(state.lines)
        lines[file_index] = normalized
        _update_rules_locked(new_lines=lines)
        return rule_id, normalized


def delete_rule_line(*, rule_id: int) -> None:
    if not isinstance(rule_id, int):
        raise TypeError("rule_id must be an int")
    if rule_id < 0:
        raise ValueError("rule_id must be >= 0")

    with _LOCK:
        state = _load_state_locked()
        if rule_id >= len(state.rule_line_indexes):
            raise IndexError(f"rule_id out of range: {rule_id}")
        file_index = state.rule_line_indexes[rule_id]

        lines = list(state.lines)
        lines.pop(file_index)
        _update_rules_locked(new_lines=lines)


def build_direct_edge_rule_map() -> Mapping[tuple[str, str], int]:
    """Map directed (src, dst) edges to the rule_id that created them.

    Only includes implication-style edges where the LHS is exactly one TagAtom.
    Matcher rules are ignored.
    """
    with _LOCK:
        state = _load_state_locked()
        out: dict[tuple[str, str], int] = {}
        for rule_id, file_index in enumerate(state.rule_line_indexes):
            line = state.lines[file_index].strip()
            if line == "":
                continue
            rules = parse_rules_text(text=f"{line}\n", filename=f"ontology_rules.txt:{rule_id}")
            for rule in rules:
                if len(rule.lhs) != 1:
                    continue
                atom = rule.lhs[0]
                if not isinstance(atom, TagAtom):
                    continue
                edge = (atom.tag, rule.rhs)
                if edge not in out:
                    out[edge] = rule_id
        return out


def rename_tag_everywhere(*, old: str, new: str) -> None:
    if not isinstance(old, str) or old.strip() == '':
        raise TypeError('old must be a non-empty string')
    if not isinstance(new, str) or new.strip() == '':
        raise TypeError('new must be a non-empty string')

    old_tag = old.strip()
    new_tag = new.strip()

    if old_tag == new_tag:
        raise ValueError('old and new tags must differ')

    with _LOCK:
        state = _load_state_locked()
        lines = list(state.lines)
        for idx, line in enumerate(lines):
            lines[idx] = _replace_tag_tokens_in_line(line=line, old=old_tag, new=new_tag)
        _update_rules_locked(new_lines=lines)


def extract_ontology_tags(ontology: TagOntology) -> set[str]:
    tags: set[str] = set()
    for src, outs in ontology.implication_out_edges.items():
        if src:
            tags.add(src)
        for dst in outs:
            if dst:
                tags.add(dst)
    for src, outs in ontology.implication_closure.items():
        if src:
            tags.add(src)
        for dst in outs:
            if dst:
                tags.add(dst)
    for src, outs in ontology.implied_by_closure.items():
        if src:
            tags.add(src)
        for dst in outs:
            if dst:
                tags.add(dst)
    for member in ontology.scc_members_by_tag.values():
        for tag in member:
            if tag:
                tags.add(tag)
    return tags
