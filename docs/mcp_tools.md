# MCP Tools (Phase 1 Read-Only)

This document defines the Phase 1 MCP interface for MetaList.

## Transport
- App-integrated HTTP JSON-RPC endpoint: `POST /api2/mcp` (auto-available when `python main.py` is running).
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
python mcp_client.py web --port 8765
```

Auto-start behavior:
- Running `python main.py` starts the main app and also launches the agent web app sidecar (default `http://127.0.0.1:8765`).

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

Output fields:
- `parent_id`
- `children` (ordered note IDs)
- `returned_count`

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
- `preview_text`

## Security / Policy
- Tool surface is read-only by policy.
- No create/edit/delete/propose/apply MCP tools are exposed in Phase 1.
