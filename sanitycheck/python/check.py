#!/usr/bin/env python3

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    rule_id: str
    message: str
    path: str
    lineno: int
    col: int
    codeframe: str


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def _load_config(config_path: str) -> dict:
    config_text = _read_text(config_path)
    config = json.loads(config_text)

    assert isinstance(config, dict)
    assert config["exclude_dot_folders"] is True
    assert isinstance(config["ignore_globs"], list)

    python_cfg = config["python"]
    js_cfg = config["js"]

    assert isinstance(python_cfg, dict)
    assert isinstance(js_cfg, dict)

    assert isinstance(python_cfg["allowed_try_callee_prefixes"], list)
    assert isinstance(python_cfg["allowed_exception_names"], list)
    assert isinstance(python_cfg["max_try_body_lines"], int)

    assert isinstance(js_cfg["allowed_try_callee_names"], list)
    assert isinstance(js_cfg["allowed_try_callee_prefixes"], list)

    return config


def _path_rel(repo_root: str, path: str) -> str:
    rel = os.path.relpath(path, repo_root)
    if rel == ".":
        return path
    return rel


def _suppressed(lines: list[str], lineno: int, rule_id: str) -> bool:
    assert lineno >= 1
    pattern = re.compile(rf"lint: allow-{re.escape(rule_id)}\\s+rationale=\".+\"")
    idx = lineno - 1

    if idx < len(lines):
        if pattern.search(lines[idx]) is not None:
            return True
    if idx - 1 >= 0:
        if pattern.search(lines[idx - 1]) is not None:
            return True
    return False


def _codeframe(lines: list[str], lineno: int, col: int, context_lines: int) -> str:
    assert lineno >= 1
    assert col >= 0
    assert context_lines >= 0

    start = lineno - context_lines
    if start < 1:
        start = 1
    end = lineno + context_lines
    if end > len(lines):
        end = len(lines)

    width = len(str(end))
    out: list[str] = []
    i = start
    while i <= end:
        prefix = str(i).rjust(width)
        out.append(f"{prefix} | {lines[i - 1]}")
        if i == lineno:
            marker = " " * (width + 3 + col) + "^"
            out.append(marker)
        i += 1
    return "\n".join(out)


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        if base is None:
            return None
        return base + "." + node.attr
    return None


def _iter_exception_names(handler_type: ast.AST) -> list[str] | None:
    if isinstance(handler_type, ast.Tuple):
        names: list[str] = []
        for elt in handler_type.elts:
            name = _dotted_name(elt)
            if name is None:
                return None
            names.append(name)
        return names

    single = _dotted_name(handler_type)
    if single is None:
        return None
    return [single]


def _max_end_lineno(node: ast.AST) -> int:
    max_line = 0
    for sub in ast.walk(node):
        end_lineno = getattr(sub, "end_lineno", None)
        lineno = getattr(sub, "lineno", None)
        if isinstance(end_lineno, int):
            if end_lineno > max_line:
                max_line = end_lineno
        elif isinstance(lineno, int):
            if lineno > max_line:
                max_line = lineno
    return max_line


def _contains_raise(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Raise):
            return True
    return False


def _contains_return(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return):
            return True
    return False


def _try_has_allowlisted_call(try_node: ast.Try, allowed_prefixes: list[str]) -> bool:
    assert isinstance(allowed_prefixes, list)
    for stmt in try_node.body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call):
                callee = _dotted_name(sub.func)
                if callee is None:
                    continue
                for prefix in allowed_prefixes:
                    if callee.startswith(prefix):
                        return True
    return False


def _is_value_context(parent: ast.AST, field_name: str) -> bool:
    if isinstance(parent, ast.Assign) and field_name == "value":
        return True
    if isinstance(parent, ast.AnnAssign) and field_name == "value":
        return True
    if isinstance(parent, ast.Return) and field_name == "value":
        return True
    if isinstance(parent, ast.keyword) and field_name == "value":
        return True
    if isinstance(parent, ast.Call):
        if field_name == "args":
            return True
        if field_name == "keywords":
            return True
    return False


class _Checker(ast.NodeVisitor):
    def __init__(
        self,
        *,
        path: str,
        repo_root: str,
        source_text: str,
        config: dict,
    ):
        self._path = path
        self._repo_root = repo_root
        self._source_text = source_text
        self._lines = source_text.splitlines()
        self._config = config
        self._violations: list[Violation] = []

        self._dict_like_names: set[str] = set()

        self._parent_stack: list[tuple[ast.AST, str]] = []

    def violations(self) -> list[Violation]:
        return list(self._violations)

    def _index_dict_like_names(self, tree: ast.AST) -> None:
        dict_like: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Name):
                    dict_like.add(node.value.id)

            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    annotation = _dotted_name(node.annotation)
                    if annotation is not None:
                        if annotation == "dict" or annotation.endswith(".dict"):
                            dict_like.add(node.target.id)

            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Dict):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            dict_like.add(target.id)
                if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                    if node.value.func.id == "dict":
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                dict_like.add(target.id)

        self._dict_like_names = dict_like

    def _add(self, *, node: ast.AST, rule_id: str, message: str) -> None:
        lineno = getattr(node, "lineno", None)
        col = getattr(node, "col_offset", None)
        if not isinstance(lineno, int):
            lineno = 1
        if not isinstance(col, int):
            col = 0

        if _suppressed(self._lines, lineno, rule_id):
            return

        frame = _codeframe(self._lines, lineno, col, 2)
        violation = Violation(
            rule_id=rule_id,
            message=message,
            path=_path_rel(self._repo_root, self._path),
            lineno=lineno,
            col=col,
            codeframe=frame,
        )
        self._violations.append(violation)

    def generic_visit(self, node: ast.AST) -> None:
        for field_name, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        self._parent_stack.append((node, field_name))
                        self.visit(item)
                        self._parent_stack.pop()
            elif isinstance(value, ast.AST):
                self._parent_stack.append((node, field_name))
                self.visit(value)
                self._parent_stack.pop()

    def visit_Try(self, node: ast.Try) -> None:
        python_cfg = self._config["python"]
        allowed_prefixes = python_cfg["allowed_try_callee_prefixes"]
        allowed_exceptions = python_cfg["allowed_exception_names"]
        max_try_lines = python_cfg["max_try_body_lines"]

        if len(node.handlers) == 0:
            self._add(node=node, rule_id="PY001", message="try without except is forbidden")
            self.generic_visit(node)
            return

        if not _try_has_allowlisted_call(node, allowed_prefixes):
            self._add(node=node, rule_id="PY001", message="try body has no allowlisted external call")

        start_line = getattr(node, "lineno", None)
        if not isinstance(start_line, int):
            start_line = 1
        end_line = getattr(node, "end_lineno", None)
        if not isinstance(end_line, int):
            end_line = _max_end_lineno(node)
        line_count = end_line - start_line + 1
        if line_count > max_try_lines:
            self._add(
                node=node,
                rule_id="PY001",
                message=f"try body too large ({line_count} lines > {max_try_lines})",
            )

        for handler in node.handlers:
            if handler.type is None:
                self._add(node=handler, rule_id="PY001", message="bare except is forbidden")
                continue

            names = _iter_exception_names(handler.type)
            if names is None:
                self._add(node=handler, rule_id="PY001", message="except type must be a simple name")
                continue

            for exc_name in names:
                if exc_name == "Exception" or exc_name == "BaseException":
                    self._add(node=handler, rule_id="PY001", message=f"forbidden exception type: {exc_name}")
                    continue
                if exc_name not in allowed_exceptions:
                    self._add(
                        node=handler,
                        rule_id="PY001",
                        message=f"exception type not allowlisted: {exc_name}",
                    )

            if _contains_return(handler):
                self._add(node=handler, rule_id="PY001", message="except handler must not return")
            if not _contains_raise(handler):
                self._add(node=handler, rule_id="PY001", message="except handler must raise")

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_defaults(node)
        self.generic_visit(node)

    def _check_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = node.args
        if len(args.defaults) != 0:
            self._add(node=node, rule_id="PY002", message="default parameters are forbidden")
        for kw_default in args.kw_defaults:
            if kw_default is not None:
                self._add(node=node, rule_id="PY002", message="default parameters are forbidden")
                break

    def visit_Call(self, node: ast.Call) -> None:
        self._check_default_value_apis(node)
        self.generic_visit(node)

    def _check_default_value_apis(self, node: ast.Call) -> None:
        callee = _dotted_name(node.func)
        if callee is not None:
            if callee == "os.getenv":
                self._add(node=node, rule_id="PY003", message="os.getenv(...) is forbidden")
                return
            if callee == "os.environ.get":
                self._add(node=node, rule_id="PY003", message="os.environ.get(...) is forbidden")
                return
            if callee == "collections.defaultdict":
                self._add(node=node, rule_id="PY003", message="collections.defaultdict(...) is forbidden")
                return
            if callee == "next":
                if len(node.args) >= 2:
                    self._add(node=node, rule_id="PY003", message="next(it, default) is forbidden")
                    return
            if callee == "dataclasses.field" or callee == "field":
                for kw in node.keywords:
                    if kw.arg == "default" or kw.arg == "default_factory":
                        self._add(node=node, rule_id="PY003", message="dataclasses.field(default=...) is forbidden")
                        return
            if callee == "pydantic.Field" or callee == "Field":
                for kw in node.keywords:
                    if kw.arg == "default" or kw.arg == "default_factory":
                        self._add(node=node, rule_id="PY003", message="pydantic.Field(default=...) is forbidden")
                        return

        if isinstance(node.func, ast.Attribute):
            is_dict_like = False
            if isinstance(node.func.value, ast.Dict):
                is_dict_like = True
            elif isinstance(node.func.value, ast.Name):
                is_dict_like = node.func.value.id in self._dict_like_names

            if is_dict_like:
                if node.func.attr == "get":
                    self._add(node=node, rule_id="PY003", message="dict.get(...) is forbidden")
                    return
                if node.func.attr == "setdefault":
                    self._add(node=node, rule_id="PY003", message="dict.setdefault(...) is forbidden")
                    return
                if node.func.attr == "pop":
                    if len(node.args) >= 2:
                        self._add(node=node, rule_id="PY003", message="dict.pop(key, default) is forbidden")
                        return

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, ast.Or):
            if len(self._parent_stack) != 0:
                parent, field_name = self._parent_stack[-1]
                if _is_value_context(parent, field_name):
                    self._add(node=node, rule_id="PY004", message="defaulting via 'or' is forbidden")
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        if len(self._parent_stack) != 0:
            parent, field_name = self._parent_stack[-1]
            if _is_value_context(parent, field_name):
                self._add(node=node, rule_id="PY004", message="defaulting via conditional expression is forbidden")
        self.generic_visit(node)


def _load_files0(files0_from: str) -> list[str]:
    data = _read_bytes(files0_from)
    parts = data.split(b"\0")
    out: list[str] = []
    for part in parts:
        if len(part) == 0:
            continue
        out.append(part.decode("utf-8"))
    return out


def _render_report(violations: list[Violation]) -> str:
    out: list[str] = []
    for v in violations:
        out.append(f"{v.path}:{v.lineno}:{v.col} {v.rule_id} {v.message}")
        out.append(v.codeframe)
        out.append("")
    out.append(f"Total: {len(violations)}")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--files0-from", required=True)
    parser.add_argument(
        "--max-violations",
        type=int,
        default=200,
        help="Cap printed violations (still exits 1 if more exist)",
    )
    args = parser.parse_args()

    config = _load_config(args.config)
    files = _load_files0(args.files0_from)
    max_violations = args.max_violations
    assert isinstance(max_violations, int)
    assert max_violations >= 1

    violations: list[Violation] = []

    for path in files:
        source_text = _read_text(path)
        tree = ast.parse(source_text, filename=path)
        checker = _Checker(path=path, repo_root=args.repo_root, source_text=source_text, config=config)
        checker._index_dict_like_names(tree)
        checker.visit(tree)
        violations.extend(checker.violations())

    if len(violations) != 0:
        shown = violations[:max_violations]
        sys.stdout.write(_render_report(shown))
        if len(violations) > max_violations:
            sys.stdout.write(f"(truncated) Remaining: {len(violations) - max_violations}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
