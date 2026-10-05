# Legacy regression cases (not run)

These cases tested the up-front routing design that the tool-using agent replaced:
the `route`, `help`, `respond`, `web_action` and `web_respond` stages. Those
production builders no longer exist, so these files are no longer loaded by
`python -m evals run`.

They are kept only as fixed inputs and reviewed expectations to migrate into
agent-stage cases (PLAN.md, Phase 6). Migration keeps each scenario's inputs and
the behavior it expected; it never changes an expectation just to make the new
design pass. Once a case is migrated or deliberately retired, delete it here.

The `help`, `actions`, `selected-note` and `web` folders keep their original
READMEs and recorded results for reference.
