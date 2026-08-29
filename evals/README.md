# Live Ollama Agent Evaluations

These behavioral evaluations call MetaList's real managed Ollama server and are
intentionally excluded from normal `pytest` discovery. Run them after changing
agent prompts, schemas, routing policy, evidence payloads, or harness orchestration:

```bash
METALIST_LIVE_OLLAMA_MODEL=qwen2.5:7b-instruct \
  .venv/bin/pytest -q -s evals/test_live_ollama_agent.py
```

The suite uses synthetic note content. It reports and asserts the model's initial
route choice, the Instructor-validated route, attempt count, evidence action,
source selection, final citation, and elapsed time. Failures are behavioral signal;
do not weaken assertions merely because a local model is nondeterministic.
