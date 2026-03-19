# MCP Tools (Phase 1 Read-Only)

This document defines the Phase 1 MCP interface for MetaList.

## Transport
- App-integrated HTTP JSON-RPC endpoint: `POST /api2/mcp` (auto-available while a MetaList namespace process is running).
- Namespace is implicit in the MetaList process you started. If that process was launched with `--namespace work`, the integrated MCP endpoint is serving the `work` database.
- Local stdio endpoint (manual/advanced):

```bash
python -m app.mcp
```

Client helper:

```bash
python mcp_client.py cli tools/list
python mcp_client.py cli tools/call health_check '{}'
```

Agentic web app helper (separate port, Ollama-backed):

```bash
python mcp_client.py web --port 8765 --mcp-url http://127.0.0.1:8000/api2/mcp
```

Auto-start behavior:
- Plain `python main.py` from a source checkout now restarts already-running namespaces from the current checkout, launches stopped namespaces with their saved/default profiles, prints their URLs, and exits.
- `python main.py work` or `python main.py --namespace work` starts one main app process and also launches that namespace's agent web app sidecar.
- The auto-started sidecar now points at the resolved MCP URL for that MetaList process, so changing the main HTTP port does not require a manual MCP URL override.
- Namespace launch profiles live in `~/MetaList/namespaces.db`, so after a first explicit run you can use `python main.py work` and the sidecar will reuse the saved ports for `work`.
- Use `python main.py --mcp-port 8766 ...` when you want a second MetaList instance to auto-start its own sidecar without reusing `8765`.
- Standalone `mcp_client.py` remains URL-driven, not namespace-driven: point it at the server URL you want, and that server's process namespace determines the data it can see.

## Readiness
- Most tools require the in-memory note store to be loaded.
- If the vault is locked or not hydrated, tools return an error: `Vault locked or not hydrated`.

## Tool Catalog

### `health_check`
Input:
```json
{}
```

Output fields:
- `server`
- `version`
- `ready`

### `count_notes`
Input:
```json
{}
```

Output fields:
- `total_notes`

### `get_note`
Input:
```json
{
  "note_id": "..."
}
```

Returns one note with full descendant subtree in one response.

Node shape:
- `note`
  - `id`, `parent_id`, `prev_id`, `next_id`
  - `is_collapsed`
  - `content`
  - `created_at`, `updated_at`
- `tags`
  - `raw_tag_string`
  - `tag_terms`
  - `implied_tag_terms`
  - `effective_tag_terms`
- `children` (recursive node array)

### `list_children`
Input:
```json
{
  "parent_id": null
}
```

Notes:
- Use `parent_id = null` for root notes.
- Use a note ID string for direct children.
- Returns a bounded window of full child note objects (currently first 25, not an unbounded ID dump).

Output fields:
- `parent_id`
- `total_children`
- `returned_count`
- `has_more`
- `children[]`
  - `note`
    - `id`, `parent_id`, `prev_id`, `next_id`
    - `is_collapsed`, `content`, `created_at`, `updated_at`
  - `tags`
    - `raw_tag_string`, `tag_terms`, `implied_tag_terms`, `effective_tag_terms`
  - `child_count`

### `list_tags`
Input:
```json
{
  "prefix": "",
  "limit": 20
}
```

Output fields:
- `prefix`
- `limit`
- `total_matches`
- `returned_count`
- `tags` (`[{ "tag": "...", "count": N }]`)

### `search_notes`
Input:
```json
{
  "query": "",
  "required_tags": [],
  "forbidden_tags": [],
  "limit": 50,
  "offset": 0
}
```

Output fields:
- `query`
- `required_tags`
- `forbidden_tags`
- `resolved_query`
- `limit`
- `offset`
- `total_matches`
- `returned_count`
- `results`

Each `results[]` item includes:
- `note_id`
- `parent_id`
- `updated_at`
- `raw_tag_string`
- `tag_terms`
- `implied_tag_terms`
- `effective_tag_terms`
- `preview_text`

## Security / Policy
- Tool surface is read-only by policy.
- No create/edit/delete/propose/apply MCP tools are exposed in Phase 1.
