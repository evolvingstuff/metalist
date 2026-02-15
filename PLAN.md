# PLAN.md — Phase 1 Read-Only MCP (stdio-first)

## 0. Goal
- Add a production-safe **Phase 1 MCP server** that is:
  - read-only
  - local stdio transport first
  - aligned to existing MetaList auth/encryption/runtime constraints
- Keep implementation structured so MCP-over-HTTP can be added later without rewriting tool logic.

## 1. Scope (Phase 1 only)

### In scope
- MCP stdio server entrypoint.
- Read-only tools for note retrieval and search.
- Clear locked/unavailable behavior when note data is not hydrated.
- Documentation for setup, tool catalog, and security posture.
- Automated tests for tool handlers and permission boundaries.

### Out of scope (explicitly later)
- Proposal flow.
- Append or any write operations.
- Patch application.
- MCP HTTP transport.

## 2. Design decisions for this phase

### Transport
- **stdio only** in Phase 1.
- No MCP HTTP endpoint yet.

### Capability surface
- Expose read-only tools only.
- No mutation endpoints or hidden write side-effects.

### Architecture boundary (to avoid rewrite later)
- Split MCP code into:
  - transport adapter (`stdio`)
  - transport-agnostic tool handlers (core)
  - shared guards/policy checks
- Future HTTP transport reuses the same core handlers.

## 3. Proposed tool set (v1 read-only)
- `health_check()`
  - returns server/version/ready state.
- `get_note(note_id)`
  - returns canonical note payload plus full descendant subtree in one response:
    - `note` object (id, parent/prev/next, content, timestamps)
    - `tags` object with explicit tag provenance:
      - `raw_tag_string` (stored tag bar string)
      - `tag_terms` (normalized terms parsed directly from this note's tag bar)
      - `implied_tag_terms` (ontology implication closure terms implied from effective base terms)
      - `effective_tag_terms` (final normalized set used for retrieval/search context)
    - `children` recursive array (same shape) so clients do not recurse with repeated calls.
- `list_children(parent_id)`
  - returns ordered child IDs for tree traversal (`parent_id=null` for roots).
- `list_tags(prefix, limit)`
  - returns known tags (optionally prefix-filtered) for discovery/autocomplete.
- `search_notes(query, required_tags, forbidden_tags)`
  - returns matching note IDs + compact metadata with explicit tag filters.

Notes:
- Tool arguments are strict and explicit.
- Unknown note IDs fail loudly.
- No implicit fallbacks.

## 4. Implementation steps

### Step A — MCP package scaffold
- Add `app/mcp/` package with:
  - `server.py` (stdio adapter bootstrap)
  - `tools.py` (tool registration + schemas)
  - `read_service.py` (transport-agnostic read handlers)
  - `policy.py` (read-only guard surface)
  - `errors.py` (explicit MCP-facing error mapping)

### Step B — Read handlers over existing services
- Reuse current in-memory sources:
  - `app/services/note_store.py`
  - `app/services/search_index.py`
- Add readiness guard:
  - if note store is not hydrated/loaded, fail with explicit "vault locked or not hydrated" error.
- Ensure tag data is exposed in MCP responses:
  - `get_note` includes raw vs implied vs effective tag fields
  - tag-oriented tools return deterministic normalized tag values.
- Implement subtree retrieval in `get_note`:
  - include all descendants in-order in a single response
  - keep depth-first traversal deterministic.

### Step C — Stdio entrypoint + run command
- Add a runnable entrypoint (module invocation) for local MCP clients.
- Keep startup minimal and deterministic for local developer usage.

### Step D — Documentation
- Create `docs/mcp_tools.md` (tool contracts + examples + failure modes).
- Update `README.md` with a short MCP section and run instructions.
- Update `docs/README.md` index with MCP docs links.

### Step E — Tests
- Add unit tests for:
  - `get_note` success/fail
  - `get_note` returns complete subtree for parent notes
  - `get_note` includes structured tag provenance (`tag_terms`, `implied_tag_terms`, `effective_tag_terms`)
  - `get_note` tag sets remain deterministic and deduplicated
  - `list_children` ordering/root behavior
  - `list_tags` discovery/prefix behavior
  - `search_notes` query + tag-filter behavior
  - readiness guard when store is not loaded
  - strict read-only policy (no write tools exposed)

## 5. Security and policy requirements (Phase 1)
- Read-only by construction:
  - no tool that mutates notes/tags/links/settings.
- Treat note text as untrusted content.
- No secret logging in MCP error paths.
- Error behavior remains fail-fast for internal invariants.

## 6. Acceptance criteria
- MCP stdio server starts locally and advertises only read-only tools.
- Tools can read/search current notes when store is loaded.
- `get_note` returns full descendant subtree in one call (no client recursion required).
- `get_note` returns direct vs implied vs effective tag information for each returned note.
- Tags are discoverable and usable as explicit search filters.
- Locked/unhydrated state returns explicit tool errors (not silent empty data).
- Docs exist for tool catalog and local usage.
- New tests pass.

## 7. Follow-up (Phase 2+)
- Add proposal/write tools behind explicit approval/policy gates.
- Add MCP HTTP transport adapter reusing the same tool handler core.
- Expand audit and quota controls for write-capable workflows.
