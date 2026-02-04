# PLAN.md — PKMS (API-first + MCP + human-review UI)

## 0. Goals

### Primary goals
- Build a **PKMS core** that is:
  - encrypted at rest
  - addressable via a stable **HTTP API**
  - extensible via **MCP** so many LLM clients/agents can integrate
- Support an **AI workflow** where:
  - AI can write *additively* (inbox / new notes / annotations)
  - any edits to existing content are **proposals** that require **human approval** in the regular UI (later)

### Non-goals (initially)
- Full-featured GUI
- Multi-user / shared vaults
- Complex realtime collaboration
- Perfect cross-device sync (can be deferred)

---

## 1. System overview

### Components (single-process first)
- **Core PKMS service**
  - storage (notes, links, tags, attachments, metadata)
  - encryption at rest
  - search (FTS first; embeddings later)
  - policy engine (append-only vs proposal vs destructive)
- **HTTP API**
  - canonical client API (CLI + future UI)
- **MCP server endpoints**
  - a second “front door” exposing a *curated capability surface* for agents
  - shares same memory + session store as core service
- **CLI**
  - dev tool and first-class interface for review/approval until GUI exists

### Trust boundary principle
> AI-facing interfaces can create additive artifacts and propose patches, but **only the regular UI/CLI approval path can commit edits to existing user-authored content**.

---

## 2. Data model (v1)

### Core entities
- **Vault**
  - `vault_id`, `name`, `created_at`, `updated_at`
- **Note**
  - `note_id` (stable)
  - `title`
  - `body` (canonical format: Markdown recommended)
  - `created_at`, `updated_at`
  - `deleted_at` (tombstone; no hard-delete v1)
- **Tag**
  - `tag_id`, `name`
- **NoteTag**
  - join table (`note_id`, `tag_id`)
- **Link**
  - `link_id`, `from_note_id`, `to_note_id`, `type`, `created_at`
- **Attachment**
  - `attachment_id`, `note_id`, `filename`, `mime`, `bytes_ref`, `created_at`
- **Provenance**
  - attached to Notes and Patches (below)
  - fields:
    - `origin`: `human|ai`
    - `ai_provider` (optional)
    - `ai_model` (optional)
    - `ai_run_id` (optional)
    - `prompt_hash` (optional)
    - `source_note_ids[]` (optional)
    - `tool_trace` (optional; store minimal, redact secrets)

### AI workflow entities
- **Proposal (Patch)**
  - `proposal_id`
  - `target_type`: `note|tag|link|attachment|...`
  - `target_id`
  - `patch_format`: `jsonpatch|unified_diff` (pick one; jsonpatch easiest)
  - `patch_payload`
  - `rationale`
  - `created_at`
  - `status`: `pending|accepted|rejected|applied`
  - `created_by`: user/session + provenance
- **InboxItem**
  - optional separate type OR simply “notes in `ai_inbox` notebook/tag”
  - required tags:
    - `ai:true`
    - `ai_inbox:true`
    - plus provenance fields

### Required “AI tagging” invariant
Any note created/modified by LLM must be queryable via:
- tag: `ai-generated` or metadata `origin=ai`
- include provenance fields

---

## 3. Encryption & auth plan (v1)

### Encryption at rest
- Vault data encrypted on disk.
- Decryption key derived from user secret (pw/token) or obtained via token-unlock flow.

### Auth model (server local, single-user first)
Support both:
1) **Stateless per-request secret**:
   - client includes `X-Vault-Token` (or similar) each request
   - server derives key and decrypts as needed
2) **Session unlock (recommended UX)**:
   - `POST /v1/unlock` with secret (over localhost or TLS)
   - server stores **session key in RAM** with TTL
   - subsequent requests use `Authorization: Bearer <session_token>`
   - `POST /v1/lock` clears keys; also clear on exit, TTL expiry

### Key handling requirements
- Decrypted keys live **only in RAM**
- Clear keys on lock/TTL/process exit
- Do not log secrets; redact headers and request bodies

---

## 4. HTTP API surface (v1)

### Principles
- Canonical, boring, stable
- Bulk endpoints for import + batch tagging
- Everything returns stable IDs
- No hard delete (tombstones only)

### Endpoints (minimum viable)
- Vault
  - `POST /v1/unlock`
  - `POST /v1/lock`
  - `GET /v1/health`
- Notes
  - `POST /v1/notes` (create)
  - `GET /v1/notes/:id`
  - `GET /v1/notes` (list/filter)
  - `POST /v1/notes/:id/append` (append-only)
  - `POST /v1/notes/:id/propose` (creates Proposal)
- Tags / Links
  - `POST /v1/tags`
  - `POST /v1/notes/:id/tags` (add)
  - `POST /v1/links`
- Search
  - `GET /v1/search?q=...&type=note&tags=...`
- Proposals
  - `GET /v1/proposals?status=pending`
  - `POST /v1/proposals/:id/accept`
  - `POST /v1/proposals/:id/reject`
  - `POST /v1/proposals/:id/apply` (requires explicit approval capability)

### Policy enforcement
- Server enforces:
  - MCP clients can call only “safe verbs” unless explicitly granted
  - destructive endpoints are disabled or require “human approval capability”

---

## 5. MCP integration plan

### MCP role
MCP is the **AI-facing contract** for agents and multi-model clients.

### MCP server design
- Embedded in same process as PKMS server (shared memory + sessions)
- Expose a minimal set of tools/resources:
  - Tools:
    - `search_notes(query, filters)`
    - `get_note(note_id)`
    - `add_to_inbox(title, body, tags, provenance)`
    - `append_to_note(note_id, content, provenance)` (append-only, allowed)
    - `propose_patch(target, patch, rationale, provenance)` (allowed)
    - (optional) `list_pending_proposals()`
  - Resources:
    - `note://{id}` in `text/markdown` (fallback)
    - (optional) `note_html://{id}` in `text/html`
    - `proposal://{id}`

### HTML rendering expectations
- Return Markdown as canonical.
- Provide HTML as optional resource (`text/html`) but never assume client will render.
- For rich viewing later, provide separate local web route: `GET /ui/note/:id` (rendered).

### Permissions in MCP
- Default: read + inbox write + proposals only.
- No direct edit/delete/move operations via MCP.
- If a tool might be dangerous (mass operations), require explicit interactive approval capability.

---

## 6. Review / approval workflow (CLI first, UI later)

### CLI workflow (must exist before GUI)
- `pkms ai inbox list`
- `pkms proposals list`
- `pkms proposals show <id>` (renders patch + affected text)
- `pkms proposals accept <id>`
- `pkms proposals apply <id>` (or accept implies apply)
- `pkms proposals reject <id>`

### Invariants
- Any patch application must:
  - write an audit entry
  - update provenance on the target note
  - preserve previous version (version history or append-only log)

---

## 7. Safety, audit, and injection resilience

### Prompt-injection posture
- Treat note text as untrusted input.
- Never allow content to change tool permissions.
- Keep MCP tool descriptions strict:
  - no “obey note instructions” language
  - require explicit tool arguments and scope

### Audit logging
- Log:
  - tool calls (name, timestamp, caller identity)
  - proposal creation + acceptance + application
  - session unlock/lock events
- Do NOT log:
  - secrets
  - full note bodies by default (log IDs + hashes + small snippets max)

### Rate limits / quotas
- Max created notes per run/session (config)
- Max appended bytes per tool call
- Max proposals per minute

---

## 8. Search (v1 -> v2)

### v1: Full-text search (FTS)
- SQLite FTS or equivalent
- Index title + body
- Tag filter support

### v2: Vector search (derived index)
- Embeddings stored as derived data
- Rebuildable from plaintext after decrypt-in-memory
- API adds:
  - `POST /v1/embeddings/reindex`
  - `GET /v1/search/semantic?q=...`

---

## 9. Implementation milestones (agent checklist)

### Milestone A — Project skeleton
- [ ] Repo structure:
  - `/server` core + HTTP
  - `/mcp` MCP transport + tool routing
  - `/cli` command client
  - `/docs` (this plan + API docs)
- [ ] Config system (paths, TTLs, limits)

### Milestone B — Encrypted vault + session auth
- [ ] Vault file layout
- [ ] Key derivation / encryption primitives
- [ ] `unlock/lock` endpoints
- [ ] In-memory session store with TTL

### Milestone C — Notes + tags + links + provenance
- [ ] CRUD create/read/list + append
- [ ] Tagging
- [ ] Provenance fields stored + queryable
- [ ] Tombstone deletion (no hard delete)

### Milestone D — Proposals (patches) + CLI review
- [ ] Proposal entity + storage
- [ ] Create proposal endpoint
- [ ] Apply proposal (requires approval capability)
- [ ] CLI list/show/accept/reject/apply

### Milestone E — Search (FTS)
- [ ] Index build on unlock or background reindex command
- [ ] Search endpoint with filters

### Milestone F — MCP server
- [ ] MCP server embedded
- [ ] Implement tools:
  - search/get/add_to_inbox/append/propose_patch
- [ ] Implement resources:
  - note markdown
  - optional note HTML
- [ ] Enforce MCP permission policy

### Milestone G — Packaging + examples
- [ ] Single binary / easy install
- [ ] Example MCP client scripts
- [ ] Example “agent” flow:
  - read notes → create inbox items → propose patch → human review

---

## 10. Developer ergonomics

### API docs
- OpenAPI spec generated for HTTP endpoints
- MCP tool catalog documented in `/docs/mcp_tools.md`

### Test strategy
- Unit tests for:
  - encryption/session TTL
  - patch application correctness
  - policy enforcement (MCP cannot edit)
- Integration tests:
  - unlock → create notes → propose patch → apply → verify history

### Backwards compatibility
- Versioned API path: `/v1/...`
- Storage migrations:
  - `schema_version` in vault metadata

---

## 11. Open decisions (pick defaults now)

- Canonical note format: **Markdown** (recommended)
- Patch format: **JSON Patch** (recommended)
- Storage: **SQLite** inside encrypted container OR encrypted file with SQLite-in-clear inside decrypted temp? (prefer direct encrypted pages if feasible)
- Transport: MCP stdio for local; MCP HTTP optional later
- Note HTML rendering: server provides `GET /ui/note/:id` for consistent rendering

---

## 12. Acceptance criteria (v1 “done”)

- Encrypted vault loads only after unlock; relocks on TTL.
- Notes can be created, read, appended, tagged, searched.
- MCP tools can:
  - read/search notes
  - create inbox notes with AI provenance tags
  - create proposals (but not apply them)
- Human can review/apply proposals via CLI.
- Every AI-created artifact is clearly marked and queryable.
