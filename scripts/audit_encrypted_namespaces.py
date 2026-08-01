#!/usr/bin/env python3
"""Run the MetaList encrypted-namespace storage audit from a source checkout."""

import sys

from app.encryption_audit import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
