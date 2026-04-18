from __future__ import annotations


EXCLUDE_DOT_FOLDERS = True
IGNORE_GLOBS: tuple[str, ...] = ()

PY_ALLOWED_TRY_CALLEE_PREFIXES = (
    "requests.",
    "httpx.",
    "socket.",
    "subprocess.",
    "urllib.",
)

PY_ALLOWED_EXCEPTION_NAMES = (
    "TimeoutError",
    "ConnectionError",
    "OSError",
)

JS_ALLOWED_TRY_CALLEE_NAMES = (
    "fetch",
    "JSON.parse",
)

JS_ALLOWED_TRY_CALLEE_PREFIXES = (
    "axios.",
    "fs.",
    "child_process.",
)

SANITY_PRUNE_NAMES = frozenset(
    {
        "node_modules",
        ".venv",
        "dist",
        "build",
        "coverage",
        "__pycache__",
    }
)

JS_TEST_DIR_NAMES = frozenset(
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

JS_TEST_SUFFIXES = (
    ".test.js",
    ".spec.js",
    ".test.jsx",
    ".spec.jsx",
    ".test.ts",
    ".spec.ts",
    ".test.tsx",
    ".spec.tsx",
)

JS_TEST_BASENAMES = frozenset({"cypress.config.js", "cypress.config.ts"})
JS_EXCLUDED_RELATIVE_PREFIXES = ("app/static/js/vendor/",)
