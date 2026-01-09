# sanitycheck

Repo-droppable gate that enforces:

* no `try`/`catch` except at explicitly allowlisted external boundaries
* no defaults (default params + default-value APIs + defaulting expressions)

Run:

* `./sanitycheck/run`

To narrow output while iterating, pass a path:

* `./sanitycheck/run src/`
* `./sanitycheck/run path/to/file.py`

## Fixer (optional)

`./sanitycheck/fix` applies mechanical refactors.

List available fixes:

* `./sanitycheck/fix --list`

If you're running from an IDE (no CLI args), run:

* `python3 sanitycheck/fix.py`

Dry run a fix:

* `./sanitycheck/fix --apply PYFIX001 --dry-run src/`
* `./sanitycheck/fix --apply PYFIX002 --dry-run src/`

Apply a fix in-place:

* `./sanitycheck/fix --apply PYFIX001 src/`
* `./sanitycheck/fix --apply PYFIX002 src/`

Notes:

* `PYFIX001` intentionally skips decorator contexts (e.g. FastAPI `@router.get("/path")`).

Install deps:

* `./sanitycheck/install.sh`

`install.sh` uses a repo-local npm cache under `sanitycheck/js/.npm-cache/` to avoid global npm cache permission issues.

Run manually: `./sanitycheck/run`

## Configuration

Edit `sanitycheck/sanitycheck.config.json`.

Notes:

* Dot-folders (paths under `./.*`) are always excluded.
* Use `ignore_globs` as an escape hatch (e.g. to ignore a legacy subtree).

## Deploying to multiple repos

If you maintain multiple sibling repos, `claude-md/deployment.py` can copy this folder into each repo.
