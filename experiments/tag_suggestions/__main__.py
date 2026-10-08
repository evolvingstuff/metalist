"""Offline tag-suggestion experiment (PLAN.md, phase 1).

    .venv-experiments/bin/python -m experiments.tag_suggestions --namespace NAME
    .venv-experiments/bin/python -m experiments.tag_suggestions --synthetic 3000

The namespace database is copied read-only into a temporary directory, and the
copy is what gets unlocked and read; it is deleted at the end. For a
password-protected namespace you type the password at the prompt. Only totals
are printed.
"""

from __future__ import annotations

import argparse
import getpass
import importlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from loguru import logger

from experiments.tag_suggestions.snapshot import copy_database, live_database_path


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m experiments.tag_suggestions")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--namespace", help="namespace to evaluate on (read through a temporary copy)")
    source.add_argument("--synthetic", type=int, help="evaluate on a synthetic namespace with this many notes")
    parser.add_argument("--max-train-notes", type=int, default=4000)
    parser.add_argument("--max-test-notes", type=int, default=1500)
    parser.add_argument("--max-stage", type=int, default=2, help="most tags already in the bar to simulate")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--latest-only", action="store_true",
                        help="test only on the latest 20%% (skip the 60-80%% window)")
    parser.add_argument("--hide-tag-names", action="store_true",
                        help="ablation: remove each note's own tag names from its text")
    return parser.parse_args()


def _live_data_directory() -> Path:
    if "METALIST_DATA_DIRECTORY" in os.environ:
        return Path(os.environ["METALIST_DATA_DIRECTORY"])
    return Path.home() / "MetaList"


_EXPERIMENT_PACKAGES = ("numpy", "scipy", "sklearn", "lightgbm")


def _require_experiment_environment() -> None:
    missing = [name for name in _EXPERIMENT_PACKAGES if importlib.util.find_spec(name) is None]
    if missing:
        raise SystemExit(
            f"Missing {', '.join(missing)}: run this with the experiment environment, "
            "`.venv-experiments/bin/python -m experiments.tag_suggestions ...` "
            "(setup: experiments/tag_suggestions/README.md)."
        )


def main() -> None:
    arguments = _parse_arguments()
    _require_experiment_environment()
    with tempfile.TemporaryDirectory(prefix="metalist-tag-experiment-") as scratch:
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
        experiment = importlib.import_module("experiments.tag_suggestions.experiment")
        # MetaList logs every index rebuild and query at INFO; keep only warnings and errors.
        logger.remove()
        logger.add(sys.stderr, level="WARNING")
        if arguments.namespace is not None:
            corpus = importlib.import_module("experiments.tag_suggestions.extract").load_snapshot_corpus(
                password=password)
        else:
            corpus = importlib.import_module("experiments.tag_suggestions.synthetic").build_synthetic_corpus(
                seed=3, note_count=arguments.synthetic)
        experiment.run(corpus=corpus, options=experiment.Options(
            max_train_notes=arguments.max_train_notes, max_test_notes=arguments.max_test_notes,
            max_stage=arguments.max_stage, folds=arguments.folds, hide_tag_names=arguments.hide_tag_names,
            latest_only=arguments.latest_only,
        ))


if __name__ == "__main__":
    main()
