# Releasing MetaList

MetaList releases use the local Rich driver in `scripts/release.py`. The driver
does not call an LLM and does not ask a sequence of release questions. Supplying
the version on the command line authorizes that one release attempt.

Prepare the release on a feature branch, including the version change in
`app/version.py`. After review and testing, merge it to `main` and push `main`.
The automatic **Publish to PyPI** main workflow must exist for that exact commit.
Then run:

```bash
.venv/bin/python scripts/release.py 0.8.0
```

The command requires a clean `main` checkout exactly synchronized with
`origin/main`, the requested version in `app/version.py`, and GitHub credentials
available through `GITHUB_TOKEN` or the configured git credential helper. It:

1. waits for the exact main commit's complete 43-job release matrix;
2. requires every Windows, macOS, and Linux job and every supported Python
   version, including all browser smoke and soak jobs;
3. creates and pushes the annotated version tag only after that matrix passes;
4. waits for the tag matrix and GitHub Trusted Publishing job;
5. downloads the tested CI wheel and source distribution and compares their
   SHA-256 hashes with the public PyPI files; and
6. installs the public version in a new temporary environment, checks its
   dependencies and version, and exercises real HTTP/HTTPS startup outside the
   source checkout.

Failures stop the release immediately. The driver never reruns a failed workflow,
changes the source version, commits, merges, or moves an existing tag. If it is
interrupted after pushing a correct tag, run the same command again; it recognizes
the tag at the exact commit and resumes monitoring and verification. A tag that
points anywhere else is a hard failure.

The final installed-package output is saved under ignored
`logs/releases/`. A successful command prints the exact commit, GitHub workflow,
PyPI page, and log path.
