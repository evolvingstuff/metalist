from __future__ import annotations

from pathlib import Path

import pytest

from app.startup_js_sanity import assert_startup_js_sanity
from app.startup_js_sanity import discover_javascript_source_paths


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_shared_sanity_config(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "sanitycheck" / "sanitycheck.config.json",
        """{
  "exclude_dot_folders": true,
  "ignore_globs": [],
  "python": {
    "allowed_try_callee_prefixes": [],
    "allowed_exception_names": []
  },
  "js": {
    "allowed_try_callee_names": [],
    "allowed_try_callee_prefixes": []
  }
}
""",
    )


def test_discover_javascript_source_paths_excludes_vendor_and_tests(tmp_path: Path) -> None:
    _write_shared_sanity_config(tmp_path)
    included_js = tmp_path / "app" / "static" / "js" / "modules" / "main.js"
    included_ts = tmp_path / "frontend" / "src" / "widget.ts"
    excluded_vendor = tmp_path / "app" / "static" / "js" / "vendor" / "markdown-it.min.js"
    excluded_suffix_test = tmp_path / "frontend" / "src" / "widget.test.ts"
    excluded_dir_test = tmp_path / "tests" / "ui" / "helpers.js"
    excluded_venv = tmp_path / ".venv" / "lib.js"

    _write_file(included_js, "console.log('ok');\n")
    _write_file(included_ts, "export const ok = true;\n")
    _write_file(excluded_vendor, "console.log('vendor');\n")
    _write_file(excluded_suffix_test, "export const bad = true;\n")
    _write_file(excluded_dir_test, "console.log('skip');\n")
    _write_file(excluded_venv, "console.log('skip');\n")

    paths = discover_javascript_source_paths(tmp_path)
    rel_paths = [path.relative_to(tmp_path).as_posix() for path in paths]

    assert rel_paths == [
        "app/static/js/modules/main.js",
        "frontend/src/widget.ts",
    ]


def test_assert_startup_js_sanity_runs_eslint_and_reports_count(monkeypatch, tmp_path: Path, capsys) -> None:
    _write_shared_sanity_config(tmp_path)
    _write_file(tmp_path / "app" / "static" / "js" / "main.js", "console.log('ok');\n")
    _write_file(tmp_path / "frontend" / "src" / "widget.ts", "export const ok = true;\n")
    _write_file(tmp_path / "sanitycheck" / "js" / "eslint.config.mjs", "export default [];\n")
    _write_file(
        tmp_path / "sanitycheck" / "js" / "node_modules" / "eslint" / "bin" / "eslint.js",
        "console.log('eslint');\n",
    )

    commands: list[list[str]] = []

    class _Completed:
        returncode = 0

    monkeypatch.setattr("app.startup_js_sanity.shutil.which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(
        "app.startup_js_sanity.subprocess.run",
        lambda command, cwd, check: commands.append(command) or _Completed(),
    )

    assert_startup_js_sanity(tmp_path)

    captured = capsys.readouterr()
    assert "[startup] Running JS sanity checks..." in captured.out
    assert "[startup] JS sanity checks passed (2 JS/TS files)" in captured.out
    assert commands == [
        [
            "node",
            str(tmp_path / "sanitycheck" / "js" / "node_modules" / "eslint" / "bin" / "eslint.js"),
            "--config",
            str(tmp_path / "sanitycheck" / "js" / "eslint.config.mjs"),
            "--",
            str(tmp_path / "app" / "static" / "js" / "main.js"),
            str(tmp_path / "frontend" / "src" / "widget.ts"),
        ]
    ]


def test_assert_startup_js_sanity_raises_when_eslint_is_missing(tmp_path: Path, capsys) -> None:
    _write_shared_sanity_config(tmp_path)
    _write_file(tmp_path / "app" / "static" / "js" / "main.js", "console.log('ok');\n")
    _write_file(tmp_path / "sanitycheck" / "js" / "eslint.config.mjs", "export default [];\n")

    with pytest.raises(RuntimeError, match="run './sanitycheck/install.sh'"):
        assert_startup_js_sanity(tmp_path)

    captured = capsys.readouterr()
    assert "[startup] Running JS sanity checks..." in captured.out
    assert "[startup] JS sanity checks failed" in captured.out
