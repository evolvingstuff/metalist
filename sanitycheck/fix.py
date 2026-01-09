#!/usr/bin/env python3

import os
import sys
from pathlib import Path


sys.dont_write_bytecode = True


def _prompt(prompt: str) -> str:
    return input(prompt).strip()


def _import_fixer(repo_root: Path):
    python_dir = repo_root / "sanitycheck" / "python"
    sys.path.insert(0, str(python_dir))
    import fix as fixer  # type: ignore

    return fixer


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    config_path = repo_root / "sanitycheck" / "sanitycheck.config.json"
    if not config_path.is_file():
        raise RuntimeError(f"Missing config: {config_path}")

    fixer = _import_fixer(repo_root)

    print("sanitycheck fixer")
    print("=")
    print("Available fixes:")
    fixer.list_fixes()
    print("")

    fix_id = _prompt("Select fix id (e.g. PYFIX001): ")
    if fix_id == "":
        raise RuntimeError("No fix selected")

    paths_raw = _prompt("Paths to apply (blank = whole repo): ")
    targets: list[str]
    if paths_raw == "":
        targets = []
    else:
        targets = [p for p in paths_raw.split() if p != ""]

    dry_raw = _prompt("Dry run? (Y/n): ").lower()
    dry_run = dry_raw == "" or dry_raw == "y" or dry_raw == "yes"

    if dry_run:
        print("\nDry run selected: no files will be written.")
    else:
        confirm = _prompt("\nApply changes to files? Type 'apply' to confirm: ")
        if confirm != "apply":
            raise RuntimeError("Aborted")

    return fixer.apply_fixes(
        config_path=str(config_path),
        repo_root=str(repo_root),
        fix_ids=[fix_id],
        targets=targets,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
