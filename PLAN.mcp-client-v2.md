# PLAN.md — MetaList PKMS: Search-Context–Driven LLM Assistance (MCP)

## Goals

- **Privacy-centric**: never send more than necessary to the MCP client / model.
- **Fast on local models**: avoid iterative LLM-driven search/query loops.
- **User-in-control retrieval**: the user (via MetaList search UI) defines the active “search context”.
- **Reliable answers**: assistant must answer **only** from provided evidence, with citations.
- **Graceful fallback**: if the active context is too large or too broad, support paging (slower) with **explicit user permission**.

## Non-goals (for now)

- No LLM-generated query planning / iterative tool-search loops.
- No complicated compression heuristics (stopword stripping, semantic query expansion, etc.) unless real failures are observed.
- No requirement that all users have complete tag coverage (support text/regex, but the user is still the one narrowing).

---

## Core Concept: Search Context Session

MetaList maintains an ordered, filtered set of notes/nodes: the **Search Context**.

- Search context is defined entirely by:
  - text search terms (token/phrase), regex patterns
  - tags and tag negations
  - other filters (optional): note type, path, etc.
- Results have an **inherent order**:
  - **Top implies** more *important/recent/useful* (MetaList ordering).
  - Not necessarily chronological unless an explicit “sort by date” filter is applied.

### Key decision
The MCP client **never performs search**. It only receives a packaged slice of the current search context and reasons over it.

---

## System Components

### 1) MetaList Core (Local)
- Owns the note graph/tree, content, tags, and ordering.
- Executes searches and produces ordered results.
- Enforces privacy controls (never expose redacted/private segments).

### 2) MCP Server (Local)
- Exposes:
  - Search context introspection (counts, cursor, etc.)
  - Retrieval of a “context bundle” (packed evidence windows)
  - Paging controls (next/prev windows, expand note/node)
- Does **not** expose raw full corpus unless explicitly requested by the user.

### 3) MCP Client App (Local)
- Runs local model (Ollama/Qwen).
- Sends:
  - user question
  - current packed context bundle (Window 1)
- Receives:
  - answer with citations
  - or request to narrow / permission request to page further

---

## Data Model (Recommended)

### Note Tree
- `note_id`
- `title`
- `children[]` (node hierarchy)
- Node-level fields:
  - `node_id`
  - `text`
  - `children[]`
  - `redacted:boolean` (or access policy tags)
  - optional metadata: `created_at`, `modified_at`, `tags[]`, etc.

### Search Context
- `search_context_id`
- `query_spec` (text/regex/tags/negations)
- `order_mode`: `metalist` | `date` | `score` (default: `metalist`)
- `result_count`
- `cursor` for paging (note/node index)
- `results[]` are ordered references (ideally node-level):
  - `note_id`, `node_id` (or note-level if node granularity isn’t available)
  - optional: `match_reasons[]` (tag/text/regex), `score` (if you compute it)

---

## Context Bundles (What gets fed to the model)

### Bundle Philosophy
- Send *just enough* evidence to answer the question.
- Prefer **hierarchical slices** over entire notes.
- Never include redacted/private nodes.
- Preserve MetaList order.

### Bundle Structure (Suggested)
- Header:
  - `search_context_id`
  - short description of query spec (human-readable)
  - `order_mode` explanation: “Top = important/recent/useful”
  - `included_count` and `omitted_count` (or remaining count)
- Evidence blocks (ordered):
  - `rank/index`
  - `note_id/node_id`
  - breadcrumb path of headings/titles (titles-only)
  - content (full/trimmed/index view depending on tier)
  - truncation markers if applicable

### Citations
- The model must cite using stable IDs:
  - `[[note:<note_id>#node:<node_id>]]`
- Optional: include offsets for deep-linking:
  - `start_offset`, `end_offset`

---

## Packing Policy (Minimal + Deterministic)

### Budgeting
- Define an evidence budget per request:
  - token budget or char budget
  - keep headroom for instructions + answer
- Hard safety cap per note/node to prevent outliers from consuming the entire window.

### Progressive Fidelity (3-tier, optional but recommended)
Use this only if/when needed; start simple.

- **Tier A (0–50% budget): Full fidelity**
  - include full node text and children (within a depth cap)
- **Tier B (50–85% budget): Trimmed**
  - include breadcrumb + matched nodes (or first N nodes) + limited children
- **Tier C (85–100% budget): Index view**
  - titles/breadcrumbs + 1–2 line preview (no deep content)

If you want to start simpler:
- Tier A only, with per-note cap + “omitted count” footer.

### Always include
- breadcrumbs/titles (cheap and valuable)
- children context (as per app preference), but bounded:
  - max depth (e.g., 3–6)
  - max children per node (e.g., 50–200)
  - stop and annotate: “(children omitted: N)”

### Footer (User feedback)
When the bundle hits budget:
- “Context limit reached: included X notes/nodes; omitted Y.”
- Suggest: “Refine search (add tags/text/negations) to bring the right content into view.”

---

## Answering Policy (Assistant Behavior)

### Evidence-only rule
The assistant must:
- answer **only** from provided evidence blocks
- cite sources for any non-trivial claim
- if insufficient: say what is missing and recommend narrowing

### “Top implies important” rule
Unless `order_mode=date`:
- treat earlier items as higher priority/importance
- do not assume chronology

### Responses
- If answer is supported: provide answer + citations
- If not supported:
  - 1–2 bullets: what evidence is missing
  - 2–5 narrowing suggestions framed as search context edits
  - offer paging as fallback (see below)

---

## Paging Fallback (Slower Backup)

### When to use
Paging is used when:
- narrowing is insufficient or user prefers scanning
- initial window doesn’t contain enough evidence

### Core mechanism
- Break the ordered search context into windows.
- Feed:
  - Window k bundle
  - a small “evidence ledger” carried forward from prior windows

### Evidence Ledger (Structured, not prose)
Keep it small and stable:
- `candidate_answers[]` (each with citations + confidence)
- `facts[]` (each must have citations)
- `missing[]` (what would confirm/deny)
- `next_focus` (what to look for in next window)

Hard caps:
- max 3 candidates
- max 12 facts
- evict weaker/older entries as new evidence arrives

### Permission gating (important)
Do not auto-scan indefinitely.

Default flow:
1) Scan Window 1.
2) If insufficient:
   - present “omitted Y notes/nodes”
   - recommend narrowing
   - ask: “Scan next page(s)?” with options:
     - next 1 page
     - next 3 pages
     - narrow instead (recommended)

Optional: allow **one** automatic extra page only if “very close” (strong partial evidence).

### Stop conditions
Stop paging if:
- answer confidence reaches threshold with citations
- scanned N pages without progress (e.g., 3–5)
- `missing[]` doesn’t shrink after a page (context likely too broad)

Then instruct user to narrow search context.

---

## MCP Server Endpoints (Suggested)

### Search context
- `get_search_context_status(search_context_id)`:
  - query summary, order mode, result count, cursor, omitted count, etc.

### Bundle retrieval
- `get_context_bundle(search_context_id, cursor, budget, packing_mode)`:
  - returns evidence blocks + included/omitted counts
  - `packing_mode`: `full` | `progressive` | `compact`

### Paging
- `next_cursor(search_context_id, cursor)`
- `prev_cursor(search_context_id, cursor)`

### Deterministic expansions (non-search)
(Useful when the model requests more context without changing the user’s search spec.)
- `expand_node(note_id, node_id, depth=1, max_chars=...)`
- `expand_siblings(note_id, node_id, before=2, after=2, titles_only=true/false)`

---

## Implementation Sequence

1) **Bundle v1 (no paging)**
   - Pack in MetaList order until budget.
   - Enforce per-note cap.
   - Include omitted count footer.
   - Evidence-only answering + citations.

2) **Paging v1**
   - Add cursor/windows.
   - Add permission prompt when Window 1 insufficient.
   - Add evidence ledger schema + update rules.

3) **Progressive packing (optional)**
   - Introduce Tier A/B/C only if needed after observing failures.

4) **Deterministic expansions (optional)**
   - Expand node/siblings on request.

---

## Instrumentation (to avoid solving imaginary problems)

Log per request:
- total included notes/nodes
- omitted count
- largest note size included
- fraction of budget consumed by top 1 / top 5
- whether assistant answered vs asked to narrow vs requested paging
- pages scanned (if paging enabled)

Only add complexity (compression, smarter trimming) if logs show frequent budget pressure or failure.

---

## UX Notes (High leverage)

- Always show: “Included X / Omitted Y” so the user understands why narrowing matters.
- Provide narrow suggestions as edits to the user’s search context:
  - add tag / add negation / restrict to journal / add regex, etc.
- Paging should feel like an explicit “scan more” action, not a hidden background process.

---