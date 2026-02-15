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


def _env_int(name: str, default: int) -> int:
    if name not in os.environ:
        return default

    value = os.environ[name].strip()
    assert value != "", f"Empty env int: {name}"
    if value[0] in {"+", "-"}:
        assert len(value) > 1, f"Invalid integer env {name}={value!r}"
        digits = value[1:]
    else:
        digits = value
    if not digits.isdigit():
        raise ValueError(f"Invalid integer env {name}={value!r}")
    return int(value)


# Development settings - CRASH SERVER ON ANY ERROR
CRASH_SERVER_ON_FAIL = _env_flag("CRASH_SERVER_ON_FAIL", True)
DEV_ENFORCE_INTEGRITY_CHECKS = _env_flag("DEV_ENFORCE_INTEGRITY_CHECKS", False)
DISABLE_UNDO_SNAPSHOT = _env_flag("DISABLE_UNDO_SNAPSHOT", True)

# Tag suggestions
TAG_SUGGESTION_CONNECTORS = "-_/."

# Authentication configuration
TOKEN_EXPIRY_MINUTES = 30  # Token expires after 30 minutes of inactivity
KDF_TIME_COST = _env_int("KDF_TIME_COST", 3)
KDF_MIN_TIME_COST = 1
KDF_MAX_TIME_COST = 10
KDF_MEMORY_COST_KIB = _env_int("KDF_MEMORY_COST_KIB", 65_536)
KDF_MIN_MEMORY_COST_KIB = 8_192
KDF_MAX_MEMORY_COST_KIB = 1_048_576
KDF_PARALLELISM = _env_int("KDF_PARALLELISM", 4)
KDF_MIN_PARALLELISM = 1
KDF_MAX_PARALLELISM = 16
KDF_ALGORITHM = "ARGON2ID"
VAULT_VERSION = 3

# Login brute-force mitigation
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = _env_int("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 5)
LOGIN_RATE_LIMIT_WINDOW_SECONDS = _env_int("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300)
LOGIN_RATE_LIMIT_BLOCK_SECONDS = _env_int("LOGIN_RATE_LIMIT_BLOCK_SECONDS", 300)

# Runtime memory-hardening checks
SECURITY_HARDENING_ENABLED = _env_flag("SECURITY_HARDENING_ENABLED", True)
SECURITY_REQUIRE_ENCRYPTED_SWAP = _env_flag("SECURITY_REQUIRE_ENCRYPTED_SWAP", True)
SECURITY_REQUIRE_MACOS_NO_HIBERNATION = _env_flag("SECURITY_REQUIRE_MACOS_NO_HIBERNATION", True)

assert KDF_MIN_TIME_COST <= KDF_TIME_COST <= KDF_MAX_TIME_COST
assert KDF_MIN_MEMORY_COST_KIB <= KDF_MEMORY_COST_KIB <= KDF_MAX_MEMORY_COST_KIB
assert KDF_MIN_PARALLELISM <= KDF_PARALLELISM <= KDF_MAX_PARALLELISM
assert LOGIN_RATE_LIMIT_MAX_ATTEMPTS > 0
assert LOGIN_RATE_LIMIT_WINDOW_SECONDS > 0
assert LOGIN_RATE_LIMIT_BLOCK_SECONDS > 0

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
