# PLAN.md — MCP Client v2 (Context Window + Conversation, No Hidden Retrieval Logic)

## 0. Objective
Rewrite the MCP client around a simple, transparent loop:
1. Build a context window from current MetaList search results.
2. Prompt the model with system prompt + context window + conversation history.
3. Return plain-text assistant output.
4. Rebuild context window on every turn so UI search changes apply immediately.

This is a rewrite from scratch, kept as a separate app for now.

## 1. Locked Decisions
1. Separate app for now (not merged into main MetaList app yet).
2. Source data is redaction-processed search results from MetaList.
3. Model context includes ancestor and descendant text exactly as redaction/export logic allows.
4. No note IDs in model prompt for v1 (citations/refs deferred).
5. Preserve MetaList result order; model does not reorder retrieval.
6. No per-note cap in v1; use a total token/character context budget only.
7. Show how many notes were included vs omitted from context window.
8. Paging/deeper retrieval loops are deferred to a later version.
9. Output is plain text.
10. If confidence is low, assistant should ask clarifying questions and/or suggest narrowing search scope.
11. No hidden defaults, no silent fallbacks, no implicit “helpful” behavior.
12. Conversation UI must use a familiar chat/texting layout:
    - user messages right-aligned
    - assistant messages left-aligned
    - bubble-style rendering similar to common phone messaging UX
13. Include tags in model context, but only direct `raw_tags` for each note/node.
14. Do not include inherited or inferred tags in model context.
15. Preserve hierarchy in context payload with indentation.
16. Redacted branches are omitted silently (no `[redacted]` markers).
17. Include searchable plain text only; do not send raw HTML or image/binary payload data.

## 2. v1 Scope

### In Scope
- Context-window builder from active search context.
- Multi-turn conversation support.
- Full prompt visibility in UI.
- Clear progress feedback while running.
- Simple fail-fast behavior with explicit errors.

### Out of Scope (Deferred)
- Citations/clickable references.
- Paging across additional windows.
- Model-generated retrieval tools inside the loop.
- Tag-specific retrieval logic.
- Auto-optimizations like per-note caps or heuristic compression layers.

## 3. Core Runtime Model

## 3.1 Inputs per Turn
- `system_prompt` (MetaList schema + hierarchy behavior).
- `context_window` (rebuilt fresh this turn).
- `conversation_history` (user/assistant messages so far).

## 3.2 Context Window Build
- Universe = current UI search context.
  - If search box has query: use that filtered result list.
  - If empty: use global note list.
- Take notes in existing order.
- Serialize text payload only (no IDs in v1).
- Include hierarchical context based on redaction export behavior (ancestors + descendants).
- Render context text as an indented tree so hierarchy is explicit.
- For each included node/note, include direct `raw_tags` on a separate line when present.
- Exclude inherited/implied tags.
- Use plain searchable text extraction only:
  - strip/omit raw HTML markup
  - exclude image data payloads/binary blobs
- Omit redacted nodes/branches entirely without explicit redaction markers.
- Stop when token/char budget reached.
- Record:
  - total notes in universe
  - notes included in context window
  - notes omitted due to budget
  - estimated token/char usage
  - build time ms

## 3.3 Model Call
- Single assistant call per user turn in v1.
- Prompt format is explicit three-part composition:
  - system instructions
  - context window content
  - conversation history
- Return plain text only.

Example context formatting target:
```
Note content num one blah blah blah
# foo bar baz

    Note content num two yada yada
    # asdf yada
```

## 3.4 Low-Confidence Handling
- If model indicates uncertainty:
  - ask a clarifying question, or
  - suggest narrowing the search context.
- Do not invent hidden fallback retrieval logic.

## 4. UI/Trace Requirements

## 4.1 Always Visible
- Current run status with frequent updates (target: visible progress heartbeat about every second while running).
- Total runtime for current turn.
- Context window stats:
  - universe count
  - included count
  - omitted count
  - budget usage

## 4.2 Expand/Collapse Sections
- Full system prompt text (line-wrapped).
- Full context window payload sent to model (line-wrapped).
- Conversation payload sent to model.
- Raw model response.

No truncation markers like `...[truncated ...]...` in stored payloads.

## 4.3 Formatting
- Pretty-print JSON in UI where JSON is shown.
- Long strings should wrap to avoid horizontal scrolling.
- Human-readable sections should be newline/indent formatted.

## 4.4 Chat Layout
- Render the primary conversation as message bubbles in chronological order.
- User bubbles are right-aligned.
- Assistant bubbles are left-aligned.
- Keep trace/debug panels available below or beside the chat, but visually separate from the chat thread.
- Keep chat readable on desktop and mobile-width screens.

## 5. Fail-Fast + Transparency Rules
1. Missing required config/input -> explicit error, stop run.
2. Prompt composition failure -> explicit error, stop run.
3. Model malformed output (when structure is required) -> explicit error, stop run.
4. No silent retries that alter behavior invisibly.
5. No hidden fallback prompts or heuristic expression generators.
6. Every behavior-affecting parameter must be surfaced in run metadata.

## 6. Implementation Plan

## Phase A — Isolate v2 Path
- Keep existing logic available only as legacy path.
- Add new v2 runner module with minimal dependencies on old planner pipeline.
- Add explicit feature flag/mode selector between legacy and v2.

## Phase B — Context Window Builder
- Implement deterministic builder from search results with redaction-ready text export.
- Enforce total budget cutoff only.
- Emit inclusion/omission stats and timing.
- Ensure rebuild runs every turn (no stale context reuse).

## Phase C — Prompt Assembly + Multi-Turn Memory
- Implement three-part prompt composition.
- Add conversation transcript state for back-and-forth.
- Add optional “reset conversation” action in UI.
- Ensure prompt text is directly inspectable in UI.

## Phase D — v2 UI
- Replace old stage-heavy display with simple per-turn trace:
  - build context
  - model call
  - final answer
- Add progress heartbeat updates while in-flight.
- Add total compute time display.
- Add line-wrap and pretty-print improvements.

## Phase E — Error Handling + Diagnostics
- Standardize error payloads for UI.
- Surface exact failing phase and reason.
- Include timing breakdown:
  - context build ms
  - model call ms
  - total ms

## Phase F — Legacy Cleanup (After Validation)
- Remove dead planner/retrieval-repair code from v2 path.
- Keep legacy path behind explicit flag until deprecation decision.

## 7. Manual Validation Checklist (Human-Run)
1. With empty search context, ask broad question and verify included/omitted counts appear.
2. Narrow search context in UI, rerun immediately, verify context window rebuild reflects new scope.
3. Confirm prompt display shows all three prompt parts exactly.
4. Confirm no truncation markers are inserted.
5. Confirm low-confidence behavior asks clarifying question or suggests narrowing.
6. Confirm no hidden fallback stage appears in trace.
7. Confirm total runtime and per-phase timings render every turn.
8. Confirm chat bubbles render with user on right and assistant on left.

## 8. Exit Criteria for v1
- Context window rebuild per turn is stable and fast.
- Prompt visibility is complete and readable.
- Model receives only intended text payload (no hidden IDs/citations).
- Multi-turn conversation works across consecutive questions.
- Uncertainty handling is explicit and useful.
- No silent behavior changes, no fallback logic, no dead-air UI.

## 9. Deferred v2+ Items
- Paging over additional context windows.
- Citation/reference system with clickable note refs.
- Optional note IDs in prompt (only when citations are introduced).
- Additional retrieval tools and agentic multi-query loops (if reintroduced later by explicit decision).
