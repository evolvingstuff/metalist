from __future__ import annotations

from pathlib import Path


EXCLUDE_DOT_FOLDERS = True
IGNORE_GLOBS: tuple[str, ...] = ()

INSTALLED_DISTRIBUTION_SOURCE_DIR_NAMES = frozenset({"app"})
INSTALLED_DISTRIBUTION_SOURCE_FILE_NAMES = frozenset({"main.py"})

PY_ALLOWED_TRY_CALLEE_PREFIXES = (
    "requests.",
    "httpx.",
    "socket.",
    "subprocess.",
    "urllib.",
    "ollama_provider.",
    "client.get",
    "client.create_with_completion",
    "client.stream",
    "self._inference.infer_structured",
    "json.",
)

PY_ALLOWED_EXCEPTION_NAMES = (
    "TimeoutError",
    "ConnectionError",
    "OSError",
    "httpx.HTTPError",
    "json.JSONDecodeError",
    "OllamaProviderError",
    "ManagedOllamaRuntimeError",
    "asyncio.CancelledError",
    "StructuredInferenceError",
    "InstructorRetryException",
)

JS_ALLOWED_TRY_CALLEE_NAMES = (
    "fetch",
    "JSON.parse",
    "clearAiChatSession",
    "copyAiChatResponse",
    "listOllamaModels",
    "loadAiDebugSnapshot",
    "loadAiChatSession",
    "loadAgentPromptDefaults",
    "pullOllamaModel",
    "streamAiChat",
    "setAiDebugExactDetails",
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


def is_installed_distribution_root(project_root: Path) -> bool:
    assert isinstance(project_root, Path)
    return (
        not (project_root / "pyproject.toml").is_file()
        and (project_root / "main.py").is_file()
        and (project_root / "app").is_dir()
    )
