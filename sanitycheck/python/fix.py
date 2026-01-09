#!/usr/bin/env python3

import argparse
import ast
import fnmatch
import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Fix:
    fix_id: str
    description: str


AVAILABLE_FIXES = [
    Fix(
        fix_id="PYFIX001",
        description="Replace mapping.get(key) with mapping[key] (only .get(...) with exactly 1 positional arg)",
    ),
    Fix(
        fix_id="PYFIX002",
        description=(
            "Replace mapping.get(key, default) with mapping[key] "
            "(only .get(...) with exactly 2 positional args; drops the default)"
        ),
    ),
    Fix(
        fix_id="PYFIX003",
        description=(
            "Replace next(it, None) with next(it) "
            "(only built-in next(...) with 2 positional args and default None)"
        ),
    ),
    Fix(
        fix_id="PYFIX004",
        description=(
            "Replace x = y[0] if y else None with x = y[0] "
            "(only else None + test is name + body indexes same name)"
        ),
    ),
    Fix(
        fix_id="PYFIX005",
        description=(
            "Replace conditional-expression fallbacks with assert+value "
            "(e.g. return x if x is not None else Y -> assert x is not None; return x)"
        ),
    ),
    Fix(
        fix_id="PYFIX006",
        description=(
            "Rewrite conditional expressions into if/else statements "
            "(e.g. x = a if cond else b -> if cond: x = a; else: x = b)"
        ),
    ),
]


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _load_config(config_path: str) -> dict:
    config_text = _read_text(config_path)
    config = json.loads(config_text)
    assert isinstance(config, dict)
    assert config["exclude_dot_folders"] is True
    assert isinstance(config["ignore_globs"], list)
    return config


def _path_rel(repo_root: str, path: str) -> str:
    rel = os.path.relpath(path, repo_root)
    if rel == ".":
        return path
    return rel


def _discover_python_files(repo_root: str, config: dict, targets: list[str]) -> list[str]:
    assert isinstance(repo_root, str)
    assert os.path.isabs(repo_root)
    assert isinstance(targets, list)

    exclude_dot_folders = config["exclude_dot_folders"]
    ignore_globs = config["ignore_globs"]
    assert exclude_dot_folders is True

    prune_names = {
        "node_modules",
        ".venv",
        "dist",
        "build",
        "coverage",
        "__pycache__",
    }

    def ignored(rel_path: str) -> bool:
        i = 0
        while i < len(ignore_globs):
            if fnmatch.fnmatch(rel_path, ignore_globs[i]):
                return True
            i += 1
        return False

    def add_file(rel_path: str, out: list[str]) -> None:
        if ignored(rel_path):
            return
        if not rel_path.endswith(".py"):
            return
        out.append(os.path.join(repo_root, rel_path))

    def walk_root(root_rel: str, out: list[str]) -> None:
        root_abs = os.path.join(repo_root, root_rel)
        for walk_root_abs, dirs, files in os.walk(root_abs):
            rel_root = os.path.relpath(walk_root_abs, repo_root)
            if rel_root == ".":
                rel_root = ""

            kept_dirs: list[str] = []
            d = 0
            while d < len(dirs):
                name = dirs[d]

                if name in prune_names:
                    d += 1
                    continue
                if exclude_dot_folders and name.startswith("."):
                    d += 1
                    continue

                child_rel = name
                if rel_root != "":
                    child_rel = rel_root + "/" + name
                if ignored(child_rel) or ignored(child_rel + "/"):
                    d += 1
                    continue

                kept_dirs.append(name)
                d += 1
            dirs[:] = kept_dirs

            f = 0
            while f < len(files):
                name = files[f]
                rel_path = name
                if rel_root != "":
                    rel_path = rel_root + "/" + name
                add_file(rel_path, out)
                f += 1

    files: list[str] = []

    if len(targets) == 0:
        walk_root("", files)
        return sorted(set(files))

    for raw in targets:
        if os.path.isabs(raw):
            normalized_root = repo_root
            if not normalized_root.endswith(os.sep):
                normalized_root = normalized_root + os.sep
            if raw.startswith(normalized_root):
                raw = os.path.relpath(raw, repo_root)
            else:
                raise RuntimeError(f"Absolute paths outside repo are not allowed: {raw}")

        rel = os.path.normpath(raw)
        if rel == ".":
            walk_root("", files)
            continue
        if rel.startswith("../") or rel.startswith("..\\") or "/../" in rel or "\\..\\" in rel:
            raise RuntimeError(f"Paths outside repo are not allowed: {raw}")

        abs_path = os.path.join(repo_root, rel)
        if os.path.isdir(abs_path):
            walk_root(rel, files)
        elif os.path.isfile(abs_path):
            add_file(rel, files)
        else:
            raise RuntimeError(f"Target does not exist: {raw}")

    return sorted(set(files))


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: str


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    running = 0
    for line in text.splitlines(True):
        running += len(line)
        offsets.append(running)
    return offsets


def _to_offset(offsets: list[int], lineno: int, col: int) -> int:
    assert lineno >= 1
    assert col >= 0
    assert lineno < len(offsets)
    return offsets[lineno - 1] + col


def _call_span(text: str, node: ast.AST) -> tuple[int, int]:
    lineno = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    end_lineno = getattr(node, "end_lineno", None)
    end_col = getattr(node, "end_col_offset", None)

    assert isinstance(lineno, int)
    assert isinstance(col, int)
    assert isinstance(end_lineno, int)
    assert isinstance(end_col, int)

    offsets = _line_offsets(text)
    start = _to_offset(offsets, lineno, col)
    end = _to_offset(offsets, end_lineno, end_col)
    assert start <= end
    return start, end


def _node_span(text: str, node: ast.AST) -> tuple[int, int]:
    return _call_span(text, node)


def _stmt_span(text: str, node: ast.AST) -> tuple[int, int]:
    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", None)
    end_col = getattr(node, "end_col_offset", None)

    assert isinstance(lineno, int)
    assert isinstance(end_lineno, int)
    assert isinstance(end_col, int)

    offsets = _line_offsets(text)
    start = _to_offset(offsets, lineno, 0)
    end = _to_offset(offsets, end_lineno, end_col)
    assert start <= end
    return start, end


def _indent_child(indent: str) -> str:
    if "\t" in indent:
        return indent + "\t"
    return indent + "    "


def _apply_edits(text: str, edits: list[_Edit]) -> str:
    if len(edits) == 0:
        return text

    ordered = sorted(edits, key=lambda e: e.start)
    i = 0
    while i < len(ordered) - 1:
        assert ordered[i].end <= ordered[i + 1].start
        i += 1

    out = text
    for edit in reversed(ordered):
        out = out[: edit.start] + edit.replacement + out[edit.end :]
    return out


def _fix_pyfix001_get_to_subscript(path: str, repo_root: str, text: str) -> tuple[str, int]:
    tree = ast.parse(text, filename=path)
    edits: list[_Edit] = []

    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    dict_like_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                dict_like_names.add(node.value.id)

        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                annotation_src = ast.get_source_segment(text, node.annotation)
                if annotation_src is not None:
                    if annotation_src.startswith("dict") or "Mapping" in annotation_src:
                        dict_like_names.add(node.target.id)

        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Dict):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        dict_like_names.add(target.id)
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                if node.value.func.id == "dict":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            dict_like_names.add(target.id)

    def is_in_decorator_context(call_node: ast.AST) -> bool:
        cur: ast.AST | None = call_node
        while cur is not None:
            p = parent.get(id(cur))
            if p is None:
                return False
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                i = 0
                while i < len(p.decorator_list):
                    deco = p.decorator_list[i]
                    for sub in ast.walk(deco):
                        if sub is call_node:
                            return True
                    i += 1
            cur = p

        return False

    def is_dict_like_expr(expr: ast.AST) -> bool:
        if isinstance(expr, ast.Dict):
            return True
        if isinstance(expr, ast.Name):
            return expr.id in dict_like_names
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if is_in_decorator_context(node):
            continue
        if len(node.keywords) != 0:
            continue
        if len(node.args) != 1:
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get":
            continue

        if not is_dict_like_expr(node.func.value):
            continue

        base_src = ast.get_source_segment(text, node.func.value)
        key_src = ast.get_source_segment(text, node.args[0])
        call_src = ast.get_source_segment(text, node)
        assert base_src is not None
        assert key_src is not None
        assert call_src is not None

        replacement = f"{base_src}[{key_src}]"
        start, end = _call_span(text, node)
        assert text[start:end] == call_src
        edits.append(_Edit(start=start, end=end, replacement=replacement))

    new_text = _apply_edits(text, edits)
    return new_text, len(edits)


def _fix_pyfix002_get_default_to_subscript(path: str, repo_root: str, text: str) -> tuple[str, int]:
    tree = ast.parse(text, filename=path)
    edits: list[_Edit] = []

    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    dict_like_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                dict_like_names.add(node.value.id)

        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                annotation_src = ast.get_source_segment(text, node.annotation)
                if annotation_src is not None:
                    if annotation_src.startswith("dict") or "Mapping" in annotation_src:
                        dict_like_names.add(node.target.id)

        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Dict):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        dict_like_names.add(target.id)
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                if node.value.func.id == "dict":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            dict_like_names.add(target.id)

    def is_in_decorator_context(call_node: ast.AST) -> bool:
        cur: ast.AST | None = call_node
        while cur is not None:
            p = parent.get(id(cur))
            if p is None:
                return False
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                i = 0
                while i < len(p.decorator_list):
                    deco = p.decorator_list[i]
                    for sub in ast.walk(deco):
                        if sub is call_node:
                            return True
                    i += 1
            cur = p
        return False

    def is_dict_like_expr(expr: ast.AST) -> bool:
        if isinstance(expr, ast.Dict):
            return True
        if isinstance(expr, ast.Name):
            return expr.id in dict_like_names
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if is_in_decorator_context(node):
            continue
        if len(node.keywords) != 0:
            continue
        if len(node.args) != 2:
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get":
            continue

        if not is_dict_like_expr(node.func.value):
            continue

        base_src = ast.get_source_segment(text, node.func.value)
        key_src = ast.get_source_segment(text, node.args[0])
        call_src = ast.get_source_segment(text, node)
        assert base_src is not None
        assert key_src is not None
        assert call_src is not None

        replacement = f"{base_src}[{key_src}]"
        start, end = _call_span(text, node)
        assert text[start:end] == call_src
        edits.append(_Edit(start=start, end=end, replacement=replacement))

    new_text = _apply_edits(text, edits)
    return new_text, len(edits)


def _fix_pyfix003_next_default_none(path: str, repo_root: str, text: str) -> tuple[str, int]:
    tree = ast.parse(text, filename=path)
    edits: list[_Edit] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "next":
            continue
        if len(node.keywords) != 0:
            continue
        if len(node.args) != 2:
            continue
        default_expr = node.args[1]
        if not (isinstance(default_expr, ast.Constant) and default_expr.value is None):
            continue

        first_arg_src = ast.get_source_segment(text, node.args[0])
        call_src = ast.get_source_segment(text, node)
        assert first_arg_src is not None
        assert call_src is not None

        replacement = f"next({first_arg_src})"
        start, end = _call_span(text, node)
        assert text[start:end] == call_src
        edits.append(_Edit(start=start, end=end, replacement=replacement))

    new_text = _apply_edits(text, edits)
    return new_text, len(edits)


def _fix_pyfix004_ifexp_else_none_drop_none(path: str, repo_root: str, text: str) -> tuple[str, int]:
    tree = ast.parse(text, filename=path)
    edits: list[_Edit] = []

    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    def is_in_decorator_context(expr_node: ast.AST) -> bool:
        cur: ast.AST | None = expr_node
        while cur is not None:
            p = parent.get(id(cur))
            if p is None:
                return False
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for deco in p.decorator_list:
                    for sub in ast.walk(deco):
                        if sub is expr_node:
                            return True
            cur = p
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.IfExp):
            continue
        if is_in_decorator_context(node):
            continue

        if not (isinstance(node.orelse, ast.Constant) and node.orelse.value is None):
            continue

        if not isinstance(node.test, ast.Name):
            continue
        name = node.test.id

        if not isinstance(node.body, ast.Subscript):
            continue
        if not isinstance(node.body.value, ast.Name):
            continue
        if node.body.value.id != name:
            continue

        body_src = ast.get_source_segment(text, node.body)
        expr_src = ast.get_source_segment(text, node)
        assert body_src is not None
        assert expr_src is not None

        start, end = _node_span(text, node)
        assert text[start:end] == expr_src
        edits.append(_Edit(start=start, end=end, replacement=body_src))

    new_text = _apply_edits(text, edits)
    return new_text, len(edits)


def _fix_pyfix005_ifexp_fallback_to_assert(path: str, repo_root: str, text: str) -> tuple[str, int]:
    tree = ast.parse(text, filename=path)
    edits: list[_Edit] = []

    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    lines = text.splitlines(True)

    def indent_for(node: ast.AST) -> str:
        lineno = getattr(node, "lineno", None)
        col = getattr(node, "col_offset", None)
        assert isinstance(lineno, int)
        assert isinstance(col, int)
        line = lines[lineno - 1]
        return line[:col]

    def is_in_decorator_context(expr_node: ast.AST) -> bool:
        cur: ast.AST | None = expr_node
        while cur is not None:
            p = parent.get(id(cur))
            if p is None:
                return False
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for deco in p.decorator_list:
                    for sub in ast.walk(deco):
                        if sub is expr_node:
                            return True
            cur = p
        return False

    def match_assert_name_not_none(ifexp: ast.IfExp) -> tuple[str, str] | None:
        if not isinstance(ifexp.test, ast.Compare):
            return None
        test = ifexp.test
        if len(test.ops) != 1 or len(test.comparators) != 1:
            return None
        if not isinstance(test.ops[0], ast.IsNot):
            return None
        if not (isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value is None):
            return None
        if not isinstance(test.left, ast.Name):
            return None
        if not isinstance(ifexp.body, ast.Name):
            return None
        if ifexp.body.id != test.left.id:
            return None
        return test.left.id, f"{test.left.id} is not None"

    def match_assert_name_not_eq(ifexp: ast.IfExp) -> tuple[str, str] | None:
        # Match: None if name == X else name  -> assert name != X; name
        if not (isinstance(ifexp.body, ast.Constant) and ifexp.body.value is None):
            return None
        if not isinstance(ifexp.orelse, ast.Name):
            return None
        if not isinstance(ifexp.test, ast.Compare):
            return None
        test = ifexp.test
        if len(test.ops) != 1 or len(test.comparators) != 1:
            return None
        if not isinstance(test.ops[0], ast.Eq):
            return None
        if not isinstance(test.left, ast.Name):
            return None
        if ifexp.orelse.id != test.left.id:
            return None
        rhs_src = ast.get_source_segment(text, test.comparators[0])
        assert rhs_src is not None
        return test.left.id, f"{test.left.id} != {rhs_src}"

    def replace_return(node: ast.Return, *, assert_expr: str, value_expr: str) -> None:
        indent = indent_for(node)
        start, end = _stmt_span(text, node)
        replacement = f"{indent}assert {assert_expr}\n{indent}return {value_expr}"
        edits.append(_Edit(start=start, end=end, replacement=replacement))

    def replace_assign(node: ast.Assign, *, assert_expr: str, value_expr: str) -> None:
        if len(node.targets) != 1:
            return
        target_src = ast.get_source_segment(text, node.targets[0])
        assert target_src is not None
        indent = indent_for(node)
        start, end = _stmt_span(text, node)
        replacement = f"{indent}assert {assert_expr}\n{indent}{target_src} = {value_expr}"
        edits.append(_Edit(start=start, end=end, replacement=replacement))

    def replace_annassign(node: ast.AnnAssign, *, assert_expr: str, value_expr: str) -> None:
        target_src = ast.get_source_segment(text, node.target)
        annotation_src = ast.get_source_segment(text, node.annotation)
        assert target_src is not None
        assert annotation_src is not None
        indent = indent_for(node)
        start, end = _stmt_span(text, node)
        replacement = f"{indent}assert {assert_expr}\n{indent}{target_src}: {annotation_src} = {value_expr}"
        edits.append(_Edit(start=start, end=end, replacement=replacement))

    for node in ast.walk(tree):
        if not isinstance(node, ast.IfExp):
            continue
        if is_in_decorator_context(node):
            continue

        matched = match_assert_name_not_none(node)
        if matched is None:
            matched = match_assert_name_not_eq(node)
        if matched is None:
            continue

        name, assert_expr = matched
        p = parent.get(id(node))
        if p is None:
            continue

        if isinstance(p, ast.Return) and p.value is node:
            replace_return(p, assert_expr=assert_expr, value_expr=name)
        elif isinstance(p, ast.Assign) and p.value is node:
            replace_assign(p, assert_expr=assert_expr, value_expr=name)
        elif isinstance(p, ast.AnnAssign) and p.value is node:
            replace_annassign(p, assert_expr=assert_expr, value_expr=name)

    new_text = _apply_edits(text, edits)
    return new_text, len(edits)


def _fix_pyfix006_ifexp_to_if_else_stmt(path: str, repo_root: str, text: str) -> tuple[str, int]:
    tree = ast.parse(text, filename=path)
    edits: list[_Edit] = []

    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    lines = text.splitlines(True)

    def indent_for(node: ast.AST) -> str:
        lineno = getattr(node, "lineno", None)
        col = getattr(node, "col_offset", None)
        assert isinstance(lineno, int)
        assert isinstance(col, int)
        line = lines[lineno - 1]
        return line[:col]

    def is_in_decorator_context(expr_node: ast.AST) -> bool:
        cur: ast.AST | None = expr_node
        while cur is not None:
            p = parent.get(id(cur))
            if p is None:
                return False
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for deco in p.decorator_list:
                    for sub in ast.walk(deco):
                        if sub is expr_node:
                            return True
            cur = p
        return False

    def is_single_line(src: str) -> bool:
        return "\n" not in src and "\r" not in src

    def replace_return(stmt: ast.Return, ifexp: ast.IfExp) -> None:
        test_src = ast.get_source_segment(text, ifexp.test)
        body_src = ast.get_source_segment(text, ifexp.body)
        else_src = ast.get_source_segment(text, ifexp.orelse)
        assert test_src is not None
        assert body_src is not None
        assert else_src is not None
        if not (is_single_line(test_src) and is_single_line(body_src) and is_single_line(else_src)):
            return

        indent = indent_for(stmt)
        inner = _indent_child(indent)
        start, end = _stmt_span(text, stmt)
        replacement = (
            f"{indent}if {test_src}:\n"
            f"{inner}return {body_src}\n"
            f"{indent}else:\n"
            f"{inner}return {else_src}"
        )
        edits.append(_Edit(start=start, end=end, replacement=replacement))

    def replace_assign(stmt: ast.Assign, ifexp: ast.IfExp) -> None:
        if len(stmt.targets) != 1:
            return
        target_src = ast.get_source_segment(text, stmt.targets[0])
        test_src = ast.get_source_segment(text, ifexp.test)
        body_src = ast.get_source_segment(text, ifexp.body)
        else_src = ast.get_source_segment(text, ifexp.orelse)
        assert target_src is not None
        assert test_src is not None
        assert body_src is not None
        assert else_src is not None
        if not (
            is_single_line(target_src)
            and is_single_line(test_src)
            and is_single_line(body_src)
            and is_single_line(else_src)
        ):
            return

        indent = indent_for(stmt)
        inner = _indent_child(indent)
        start, end = _stmt_span(text, stmt)
        replacement = (
            f"{indent}if {test_src}:\n"
            f"{inner}{target_src} = {body_src}\n"
            f"{indent}else:\n"
            f"{inner}{target_src} = {else_src}"
        )
        edits.append(_Edit(start=start, end=end, replacement=replacement))

    def replace_annassign(stmt: ast.AnnAssign, ifexp: ast.IfExp) -> None:
        if stmt.simple != 1:
            return
        target_src = ast.get_source_segment(text, stmt.target)
        annotation_src = ast.get_source_segment(text, stmt.annotation)
        test_src = ast.get_source_segment(text, ifexp.test)
        body_src = ast.get_source_segment(text, ifexp.body)
        else_src = ast.get_source_segment(text, ifexp.orelse)
        assert target_src is not None
        assert annotation_src is not None
        assert test_src is not None
        assert body_src is not None
        assert else_src is not None
        if not (
            is_single_line(target_src)
            and is_single_line(annotation_src)
            and is_single_line(test_src)
            and is_single_line(body_src)
            and is_single_line(else_src)
        ):
            return

        indent = indent_for(stmt)
        inner = _indent_child(indent)
        start, end = _stmt_span(text, stmt)
        replacement = (
            f"{indent}if {test_src}:\n"
            f"{inner}{target_src}: {annotation_src} = {body_src}\n"
            f"{indent}else:\n"
            f"{inner}{target_src}: {annotation_src} = {else_src}"
        )
        edits.append(_Edit(start=start, end=end, replacement=replacement))

    for node in ast.walk(tree):
        if not isinstance(node, ast.IfExp):
            continue
        if is_in_decorator_context(node):
            continue

        p = parent.get(id(node))
        if p is None:
            continue
        if isinstance(p, ast.Return) and p.value is node:
            replace_return(p, node)
        elif isinstance(p, ast.Assign) and p.value is node:
            replace_assign(p, node)
        elif isinstance(p, ast.AnnAssign) and p.value is node:
            replace_annassign(p, node)

    new_text = _apply_edits(text, edits)
    return new_text, len(edits)


def list_fixes() -> None:
    for fix in AVAILABLE_FIXES:
        print(f"{fix.fix_id}: {fix.description}")


def apply_fixes(
    *,
    config_path: str,
    repo_root: str,
    fix_ids: list[str],
    targets: list[str],
    dry_run: bool,
) -> int:
    if len(fix_ids) == 0:
        raise RuntimeError("No fixes selected. Use --list, then --apply <FIX_ID>.")

    known = {f.fix_id for f in AVAILABLE_FIXES}
    for fix_id in fix_ids:
        if fix_id not in known:
            raise RuntimeError(f"Unknown fix id: {fix_id}")

    normalized_repo_root = os.path.abspath(repo_root)
    config = _load_config(config_path)
    py_files = _discover_python_files(normalized_repo_root, config, targets)

    total_edits = 0
    changed_files = 0
    for path in py_files:
        original = _read_text(path)
        updated = original
        edits_for_file = 0

        if "PYFIX001" in fix_ids:
            updated, applied = _fix_pyfix001_get_to_subscript(path, normalized_repo_root, updated)
            edits_for_file += applied

        if "PYFIX002" in fix_ids:
            updated, applied = _fix_pyfix002_get_default_to_subscript(path, normalized_repo_root, updated)
            edits_for_file += applied

        if "PYFIX003" in fix_ids:
            updated, applied = _fix_pyfix003_next_default_none(path, normalized_repo_root, updated)
            edits_for_file += applied

        if "PYFIX004" in fix_ids:
            updated, applied = _fix_pyfix004_ifexp_else_none_drop_none(path, normalized_repo_root, updated)
            edits_for_file += applied

        if "PYFIX005" in fix_ids:
            updated, applied = _fix_pyfix005_ifexp_fallback_to_assert(path, normalized_repo_root, updated)
            edits_for_file += applied

        if "PYFIX006" in fix_ids:
            updated, applied = _fix_pyfix006_ifexp_to_if_else_stmt(path, normalized_repo_root, updated)
            edits_for_file += applied

        if updated != original:
            changed_files += 1
            total_edits += edits_for_file
            rel = _path_rel(normalized_repo_root, path)
            print(f"{rel}: {edits_for_file} edit(s)")
            if not dry_run:
                _write_text(path, updated)

    print(f"Files changed: {changed_files}")
    print(f"Total edits: {total_edits}")
    if dry_run:
        print("Dry run: no files written")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--apply", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    if args.list:
        list_fixes()
        return 0

    return apply_fixes(
        config_path=args.config,
        repo_root=args.repo_root,
        fix_ids=args.apply,
        targets=args.paths,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
