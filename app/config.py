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
TEST_MODE = "--test" in sys.argv or (
    "TEST_MODE" in os.environ and os.environ["TEST_MODE"] == "1"
)

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
    DATABASE_URL = "sqlite:///./notes.db"
