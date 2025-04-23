VERSION = "0.3.0"
DATABASE_URL = "sqlite:///./notes.db"

# Cache busting timestamp - changes on every server restart
import time
CACHE_BUSTER = str(int(time.time()))
