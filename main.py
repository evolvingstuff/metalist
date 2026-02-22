import uvicorn
import logging
import os
import threading

from mcp_client import create_web_app
from mcp_client import DEFAULT_MAX_STEPS
from mcp_client import DEFAULT_MCP_URL
from mcp_client import DEFAULT_OLLAMA_CHAT_URL
from mcp_client import DEFAULT_OLLAMA_MODEL
from mcp_client import DEFAULT_PLANNER_SEED_TAG_LIMIT
from mcp_client import DEFAULT_PLANNER_TAG_COUNT_MODE
from mcp_client import DEFAULT_WEB_HOST
from mcp_client import DEFAULT_WEB_PORT

class FilterCheckUpdates(logging.Filter):
    NOISY_PATTERNS = (
        'POST /api/notes/acquire-lock',
        'POST /api2/notes/acquire-lock',
        'POST /api2/notes/release-lock',
        'GET /api/auth/sessions',
        'GET /api2/auth/status',
    )

    def filter(self, record):
        message = record.getMessage()
        return not any(pattern in message for pattern in self.NOISY_PATTERNS)


def _env_flag(name: str, default: bool) -> bool:
    if name not in os.environ:
        return default

    value = os.environ[name].strip().lower()
    assert value != "", f"Empty env flag: {name}"

    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean env flag {name}={value!r}")


def _env_int(name: str, default: int) -> int:
    if name not in os.environ:
        return default
    value = os.environ[name].strip()
    assert value != "", f"Empty env int: {name}"
    if not value.isdigit():
        raise ValueError(f"Invalid integer env {name}={value!r}")
    return int(value)


def _env_choice(name: str, default: str, allowed: set[str]) -> str:
    if name not in os.environ:
        return default
    value = os.environ[name].strip().casefold()
    assert value != "", f"Empty env choice: {name}"
    if value not in allowed:
        raise ValueError(f"Invalid choice env {name}={value!r}; allowed={sorted(allowed)}")
    return value


def _start_agent_web_sidecar() -> None:
    enabled = _env_flag("MCP_AGENT_WEB_ENABLED", True)
    if not enabled:
        print("Agent web app sidecar disabled (MCP_AGENT_WEB_ENABLED=0)")
        return

    if "MCP_AGENT_WEB_HOST" in os.environ:
        host = os.environ["MCP_AGENT_WEB_HOST"]
    else:
        host = DEFAULT_WEB_HOST
    port = _env_int("MCP_AGENT_WEB_PORT", DEFAULT_WEB_PORT)
    if "MCP_AGENT_OLLAMA_MODEL" in os.environ:
        model = os.environ["MCP_AGENT_OLLAMA_MODEL"]
    else:
        model = DEFAULT_OLLAMA_MODEL
    if "MCP_AGENT_MCP_URL" in os.environ:
        mcp_url = os.environ["MCP_AGENT_MCP_URL"]
    else:
        mcp_url = DEFAULT_MCP_URL
    if "MCP_AGENT_OLLAMA_CHAT_URL" in os.environ:
        ollama_chat_url = os.environ["MCP_AGENT_OLLAMA_CHAT_URL"]
    else:
        ollama_chat_url = DEFAULT_OLLAMA_CHAT_URL
    max_steps = _env_int("MCP_AGENT_MAX_STEPS", DEFAULT_MAX_STEPS)
    planner_seed_tag_limit = _env_int(
        "MCP_AGENT_PLANNER_SEED_TAG_LIMIT",
        DEFAULT_PLANNER_SEED_TAG_LIMIT,
    )
    planner_tag_count_mode = _env_choice(
        "MCP_AGENT_PLANNER_TAG_COUNT_MODE",
        DEFAULT_PLANNER_TAG_COUNT_MODE,
        {"effective", "raw"},
    )

    agent_app = create_web_app(
        default_model=model,
        default_max_steps=max_steps,
        default_planner_seed_tag_limit=planner_seed_tag_limit,
        default_planner_tag_count_mode=planner_tag_count_mode,
        default_mcp_url=mcp_url,
        default_ollama_chat_url=ollama_chat_url,
    )

    def _run() -> None:
        uvicorn.run(
            agent_app,
            host=host,
            port=port,
            reload=False,
            workers=1,
        )

    link = f"http://{host}:{port}"
    print(f"Agent web app: {link}")
    thread = threading.Thread(target=_run, name="mcp-agent-web", daemon=True)
    thread.start()

if __name__ == "__main__":
    # Configure logging to filter noisy polling endpoints
    logging.getLogger("uvicorn.access").addFilter(FilterCheckUpdates())
    _start_agent_web_sidecar()

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,  # Disable auto-reload
        workers=1  # Limit to a single worker  
    )
