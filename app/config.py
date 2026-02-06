import os
import sys

VERSION = "0.3.0"


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


# Development settings - CRASH SERVER ON ANY ERROR
CRASH_SERVER_ON_FAIL = _env_flag("CRASH_SERVER_ON_FAIL", True)
DEV_ENFORCE_INTEGRITY_CHECKS = _env_flag("DEV_ENFORCE_INTEGRITY_CHECKS", False)
DISABLE_UNDO_SNAPSHOT = _env_flag("DISABLE_UNDO_SNAPSHOT", True)

# Tag suggestions
TAG_SUGGESTION_CONNECTORS = "-_/."

# Authentication configuration
TOKEN_EXPIRY_MINUTES = 30  # Token expires after 30 minutes of inactivity
PW_PBKDF2_ITERATIONS = 1_000_000  # Number of iterations for app password hashing

# API prefixes (single source of truth)
# Client uses '/api2' via JS CONFIG; server uses the same here.
if "API_PREFIX" in os.environ:
    API_PREFIX = os.environ["API_PREFIX"].rstrip("/")
else:
    API_PREFIX = "/api2"

if "V1_API_PREFIX" in os.environ:
    V1_API_PREFIX = os.environ["V1_API_PREFIX"].rstrip("/")
else:
    V1_API_PREFIX = "/api"

# Check if running in test mode
if "--test" in sys.argv:
    TEST_MODE = True
else:
    TEST_MODE = "TEST_MODE" in os.environ and os.environ["TEST_MODE"] == "1"

if TEST_MODE:
    # Use test database
    DATABASE_URL = "sqlite:///./test.db"
    
    # Delete existing test.db if it exists
    if os.path.exists('./test.db'):
        os.remove('./test.db')
        print("🧪 Deleted existing test.db")
    
    print("🧪 Running in TEST MODE - using test.db")
else:
    # Use production database
    DEFAULT_DB_PATH = os.path.expanduser("~/MetaList/metalist2.db")
    DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH}"

# Enable verbose SQLite trace logging only when explicitly requested.
if "SQL_TRACE" in os.environ:
    SQL_TRACE_ENABLED = os.environ["SQL_TRACE"] == "1"
else:
    SQL_TRACE_ENABLED = False
