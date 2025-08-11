import os
import sys

VERSION = "0.3.0"

# Authentication configuration
TOKEN_EXPIRY_MINUTES = 30  # Token expires after 30 minutes of inactivity
PW_PBKDF2_ITERATIONS = 1_000_000  # Number of iterations for app password hashing

# Check if running in test mode
TEST_MODE = '--test' in sys.argv or os.environ.get('TEST_MODE') == '1'

if TEST_MODE:
    # Use test database
    DATABASE_URL = "sqlite:///./test.db"
    
    # Delete existing test.db if it exists
    import os
    if os.path.exists('./test.db'):
        os.remove('./test.db')
        print("🧪 Deleted existing test.db")
    
    print("🧪 Running in TEST MODE - using test.db")
else:
    # Use production database
    DATABASE_URL = "sqlite:///./notes.db"
