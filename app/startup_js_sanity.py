from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
from pathlib import Path


_JS_EXTENSIONS = frozenset({".js", ".jsx", ".ts", ".tsx"})
_PRUNE_NAMES = frozenset(
    {
        "sanitycheck",
        "node_modules",
        ".venv",
        "dist",
        "build",
        "coverage",
        "__pycache__",
    }
)
_JS_TEST_DIR_NAMES = frozenset(
    {
        "__tests__",
        "__mocks__",
        "test",
        "tests",
        "cypress",
        "e2e",
        "playwright",
    }
)
_JS_TEST_SUFFIXES = (
    ".test.js",
    ".spec.js",
    ".test.jsx",
    ".spec.jsx",
    ".test.ts",
    ".spec.ts",
    ".test.tsx",
    ".spec.tsx",
)
_JS_TEST_BASENAMES = frozenset({"cypress.config.js", "cypress.config.ts"})
_EXCLUDED_RELATIVE_PREFIXES = ("app/static/js/vendor/",)
_ESLINT_CHUNK_SIZE = 100


def _load_shared_sanity_config(project_root: Path) -> tuple[bool, list[str]]:
    config_path = project_root / "sanitycheck" / "sanitycheck.config.json"
    if not config_path.is_file():
        raise RuntimeError(f"JS sanity checks missing config at {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    exclude_dot_folders = config.get("exclude_dot_folders")
    ignore_globs = config.get("ignore_globs")
    if exclude_dot_folders is not True:
        raise RuntimeError("JS sanity checks require exclude_dot_folders=true")
    if not isinstance(ignore_globs, list):
        raise RuntimeError("JS sanity checks require ignore_globs to be a list")
    if not all(isinstance(item, str) for item in ignore_globs):
        raise RuntimeError("JS sanity checks require ignore_globs entries to be strings")
    return exclude_dot_folders, list(ignore_globs)


def _ignored(*, rel_path: str, ignore_globs: list[str]) -> bool:
    for pattern in ignore_globs:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def _is_js_test_file(rel_path: str) -> bool:
    parts = rel_path.split("/")
    if len(parts) > 1:
        for directory_name in parts[:-1]:
            if directory_name in _JS_TEST_DIR_NAMES:
                return True

    basename = parts[-1]
    if basename in _JS_TEST_BASENAMES:
        return True

    for suffix in _JS_TEST_SUFFIXES:
        if basename.endswith(suffix):
            return True
    return False


def discover_javascript_source_paths(project_root: Path) -> list[Path]:
    if not isinstance(project_root, Path):
        raise TypeError(f"project_root must be a Path, got {type(project_root)}")

    exclude_dot_folders, ignore_globs = _load_shared_sanity_config(project_root)
    paths: list[Path] = []

    for current_root, directory_names, file_names in os.walk(project_root):
        rel_root_path = Path(current_root).relative_to(project_root)
        rel_root = rel_root_path.as_posix()
        if rel_root == ".":
            rel_root = ""

        kept_dirs: list[str] = []
        for directory_name in directory_names:
            if directory_name in _PRUNE_NAMES:
                continue
            if exclude_dot_folders and directory_name.startswith("."):
                continue

            child_rel = directory_name
            if rel_root != "":
                child_rel = f"{rel_root}/{directory_name}"
            if _ignored(rel_path=child_rel, ignore_globs=ignore_globs):
                continue
            if _ignored(rel_path=f"{child_rel}/", ignore_globs=ignore_globs):
                continue
            if any(
                child_rel == prefix.removesuffix("/") or child_rel.startswith(prefix)
                for prefix in _EXCLUDED_RELATIVE_PREFIXES
            ):
                continue
            kept_dirs.append(directory_name)
        directory_names[:] = kept_dirs

        for file_name in file_names:
            if Path(file_name).suffix not in _JS_EXTENSIONS:
                continue

            rel_path = file_name
            if rel_root != "":
                rel_path = f"{rel_root}/{file_name}"
            if _ignored(rel_path=rel_path, ignore_globs=ignore_globs):
                continue
            if any(rel_path.startswith(prefix) for prefix in _EXCLUDED_RELATIVE_PREFIXES):
                continue
            if _is_js_test_file(rel_path):
                continue
            paths.append(project_root / rel_path)

    paths.sort()
    return paths


def assert_startup_js_sanity(project_root: Path) -> None:
    sanitycheck_dir = project_root / "sanitycheck"
    if not sanitycheck_dir.is_dir():
        print("[startup] JS sanitycheck not present; skipping", flush=True)
        return

    print("[startup] Running JS sanity checks...", flush=True)
    paths = discover_javascript_source_paths(project_root)
    if len(paths) == 0:
        print("[startup] JS sanity checks passed (0 JS/TS files)", flush=True)
        return

    if shutil.which("node") is None:
        print("[startup] JS sanity checks failed", flush=True)
        raise RuntimeError("JS sanity checks require node")

    eslint_bin = project_root / "sanitycheck" / "js" / "node_modules" / "eslint" / "bin" / "eslint.js"
    if not eslint_bin.is_file():
        print("[startup] JS sanity checks failed", flush=True)
        raise RuntimeError(
            f"JS sanity checks missing {eslint_bin}; run './sanitycheck/install.sh'",
        )

    eslint_config = project_root / "sanitycheck" / "js" / "eslint.config.mjs"
    if not eslint_config.is_file():
        print("[startup] JS sanity checks failed", flush=True)
        raise RuntimeError(f"JS sanity checks missing config at {eslint_config}")

    all_paths = [str(path) for path in paths]
    start_index = 0
    while start_index < len(all_paths):
        chunk = all_paths[start_index : start_index + _ESLINT_CHUNK_SIZE]
        completed = subprocess.run(
            ["node", str(eslint_bin), "--config", str(eslint_config), "--", *chunk],
            cwd=str(project_root),
            check=False,
        )
        if completed.returncode != 0:
            print("[startup] JS sanity checks failed", flush=True)
            raise RuntimeError(f"JS sanity checks failed with exit code {completed.returncode}")
        start_index += _ESLINT_CHUNK_SIZE

    print(f"[startup] JS sanity checks passed ({len(paths)} JS/TS files)", flush=True)
