from __future__ import annotations

import ast
from pathlib import Path


def test_dev_router_is_mounted_only_beneath_test_mode_guard() -> None:
    main_path = Path(__file__).resolve().parents[2] / "app" / "main.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"), filename=str(main_path))
    for parent_node in ast.walk(tree):
        for child_node in ast.iter_child_nodes(parent_node):
            child_node.parent = parent_node

    guarded_dev_mounts = 0
    unguarded_dev_mounts = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "include_router":
            continue
        if len(node.args) == 0:
            continue
        router_argument = node.args[0]
        if not isinstance(router_argument, ast.Attribute):
            continue
        if not isinstance(router_argument.value, ast.Name):
            continue
        if router_argument.value.id != "dev" or router_argument.attr != "router":
            continue

        parent = getattr(node, "parent", None)
        is_test_guarded = False
        while parent is not None:
            if isinstance(parent, ast.If) and isinstance(parent.test, ast.Name):
                if parent.test.id == "TEST_MODE":
                    is_test_guarded = True
                    break
            parent = getattr(parent, "parent", None)
        if is_test_guarded:
            guarded_dev_mounts += 1
        else:
            unguarded_dev_mounts += 1

    assert guarded_dev_mounts == 1
    assert unguarded_dev_mounts == 0
