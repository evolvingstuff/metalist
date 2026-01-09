# sanitycheck

Repo-droppable gate that enforces:

* no `try`/`catch` except at explicitly allowlisted external boundaries
* no defaults (default params + default-value APIs + defaulting expressions)

Note: default parameters are split into two rule IDs for reporting only (both are forbidden):

* `PY002`: defaults to `None`
* `PY005`: any other default

Run:

* `./sanitycheck/run`

Note: `try/finally` is allowed (it does not catch/swallow exceptions). The `try/except` form is what is restricted.

To narrow output while iterating, pass a path:

* `./sanitycheck/run src/`
* `./sanitycheck/run path/to/file.py`

## Fixer (optional)

`./sanitycheck/fix` applies mechanical refactors.

List available fixes:

* `./sanitycheck/fix --list`

Apply everything:

* `./sanitycheck/fix --apply ALL src/`

If you're running from an IDE (no CLI args), run:

* `python3 sanitycheck/fix.py`

Dry run a fix:

* `./sanitycheck/fix --apply PY003_GET_TO_SUBSCRIPT --dry-run src/`
* `./sanitycheck/fix --apply PY003_GET_DEFAULT_TO_SUBSCRIPT --dry-run src/`
* `./sanitycheck/fix --apply PY003_NEXT_NONE_TO_NEXT --dry-run src/`
* `./sanitycheck/fix --apply PY003_OS_ENVIRON_GET_TO_SUBSCRIPT --dry-run src/`
* `./sanitycheck/fix --apply PY004_IFEXP_DROP_NONE --dry-run src/`
* `./sanitycheck/fix --apply PY004_IFEXP_ASSERT --dry-run src/`
* `./sanitycheck/fix --apply PY004_IFEXP_TO_IFELSE --dry-run src/`
* `./sanitycheck/fix --apply PY002_PY005_DEF_REMOVE_DEFAULTS --dry-run src/`
* `./sanitycheck/fix --apply PY002_PY005_CALLS_EXPLICIT_DEFAULTS_AND_REMOVE --dry-run src/`

Apply a fix in-place:

* `./sanitycheck/fix --apply PY003_GET_TO_SUBSCRIPT src/`
* `./sanitycheck/fix --apply PY003_GET_DEFAULT_TO_SUBSCRIPT src/`
* `./sanitycheck/fix --apply PY003_NEXT_NONE_TO_NEXT src/`
* `./sanitycheck/fix --apply PY003_OS_ENVIRON_GET_TO_SUBSCRIPT src/`
* `./sanitycheck/fix --apply PY004_IFEXP_DROP_NONE src/`
* `./sanitycheck/fix --apply PY004_IFEXP_ASSERT src/`
* `./sanitycheck/fix --apply PY004_IFEXP_TO_IFELSE src/`
* `./sanitycheck/fix --apply PY002_PY005_DEF_REMOVE_DEFAULTS src/`
* `./sanitycheck/fix --apply PY002_PY005_CALLS_EXPLICIT_DEFAULTS_AND_REMOVE src/`

Notes:

* The `PY002_PY005_DEF_REMOVE_DEFAULTS` fix removes defaults from function signatures.
* The `PY002_PY005_CALLS_EXPLICIT_DEFAULTS_AND_REMOVE` fix only updates callsites within the same file as the function definition.

Notes:

* `PY003_GET_TO_SUBSCRIPT` intentionally skips decorator contexts (e.g. FastAPI `@router.get("/path")`).

Install deps:

* `./sanitycheck/install.sh`

`install.sh` uses a repo-local npm cache under `sanitycheck/js/.npm-cache/` to avoid global npm cache permission issues.

Run manually: `./sanitycheck/run`

## Configuration

Edit `sanitycheck/sanitycheck.config.json`.

Notes:

* Dot-folders (paths under `./.*`) are always excluded.
* Use `ignore_globs` as an escape hatch (e.g. to ignore a legacy subtree).
* The `sanitycheck/` folder itself is excluded from scanning/fixing (the gate doesn't lint its own implementation when dropped into a repo).

## Deploying to multiple repos

If you maintain multiple sibling repos, `claude-md/deployment.py` can copy this folder into each repo.
