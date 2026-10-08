"""Point MetaList's settings at a throwaway directory before any app module is imported.

app.config reads these at import time; without this the tests would resolve the
user's real data directory (~/MetaList).
"""

from __future__ import annotations

import os
import tempfile

os.environ["METALIST_DATA_DIRECTORY"] = tempfile.mkdtemp(prefix="metalist-tag-experiment-tests-")
os.environ["METALIST_NAMESPACE"] = "experiment-tests"
