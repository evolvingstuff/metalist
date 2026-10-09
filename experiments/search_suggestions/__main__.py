"""Offline search-suggestion experiment (docs/design/search-suggestion-learnings.md).

    .venv/bin/python -m experiments.search_suggestions --namespace NAME
    .venv/bin/python -m experiments.search_suggestions --synthetic 3000

The namespace database is copied read-only into a temporary directory; only the
copy is unlocked and read, and it is deleted at the end. For a password-protected
namespace you type the password at the prompt. Only totals are printed. Needs no
packages beyond MetaList's own.
"""

from __future__ import annotations

import argparse
import getpass
import importlib
import os
import sys
import tempfile
from pathlib import Path

from loguru import logger

from experiments.tag_suggestions.snapshot import copy_database, live_database_path


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m experiments.search_suggestions")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--namespace", help="namespace to evaluate on (read through a temporary copy)")
    source.add_argument("--synthetic", type=int, help="evaluate on a synthetic namespace with this many notes")
    return parser.parse_args()


def _live_data_directory() -> Path:
    if "METALIST_DATA_DIRECTORY" in os.environ:
        return Path(os.environ["METALIST_DATA_DIRECTORY"])
    return Path.home() / "MetaList"


def main() -> None:
    arguments = _parse_arguments()
    with tempfile.TemporaryDirectory(prefix="metalist-search-experiment-") as scratch:
        scratch_directory = Path(scratch)
        namespace = "experiment"
        password = ""
        if arguments.namespace is not None:
            namespace = arguments.namespace
            source = live_database_path(data_directory=_live_data_directory(), namespace=namespace)
            copy_database(source=source, scratch_data_directory=scratch_directory, namespace=namespace)
            password = getpass.getpass(f"Password for namespace {namespace!r} (Enter if it has none): ")
        # app.config reads these when first imported, so the app modules are imported
        # only now, after they point at the scratch copy.
        os.environ["METALIST_DATA_DIRECTORY"] = str(scratch_directory)
        os.environ["METALIST_NAMESPACE"] = namespace
        if "TEST_MODE" in os.environ:
            del os.environ["TEST_MODE"]
        run = importlib.import_module("experiments.search_suggestions.run")
        # MetaList logs every index rebuild and query at INFO; keep only warnings and errors.
        logger.remove()
        logger.add(sys.stderr, level="WARNING")
        if arguments.namespace is not None:
            corpus = importlib.import_module("experiments.tag_suggestions.extract").load_snapshot_corpus(
                password=password)
            history = run.load_tag_history()
        else:
            corpus = importlib.import_module("experiments.tag_suggestions.synthetic").build_synthetic_corpus(
                seed=3, note_count=arguments.synthetic)
            importlib.import_module("experiments.tag_suggestions.world_store").load_store(
                corpus=corpus, hidden_note_ids=frozenset())
            history = run.synthetic_history(corpus=corpus, seed=4)
        run.run(corpus=corpus, counts_by_date=history)


if __name__ == "__main__":
    main()
