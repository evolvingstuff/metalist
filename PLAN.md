# Server V2 Plan: Start With View Only (api2)

Owner: server/platform
Status: Revised – smallest possible start
Scope: New greenfield server in `server_v2/` mounted at `/api2` ONLY for view; frontend/client unchanged for now

## Immediate Goal
- Get `POST /api2/notes/view` returning a correct snapshot the client can consume.
- No DB reads after startup. In‑memory only. No mutations yet.
- Keep v1 intact as reference; no interweaving.

Non‑goals
- Multi‑user sync or remote collaboration.
- Cross‑process shared in‑memory state.

## Baseline (what to keep vs. replace)
Keep (only what’s strictly needed)
- Encryption primitives (DEK/AES‑GCM): `app/services/encryption.py` and compat in `app/utils/encryption.py`.

Replace (greenfield for everything else)
- API surface, services, store, transaction flow, and DB helpers: implemented fresh under `server_v2/`.
- Eliminate all runtime `allow_reads` fallbacks; v2 does not read DB after hydrate.

## First Slice Only (View)
- InMemoryStore (authoritative)
  - Unified decrypted record per note: content + parent/prev/next + flags + timestamps.
  - O(1) by‑id; O(1) head/tail/sibling navigation; RLock‑guarded.
- Strict DB Access Policy
  - Hydrate once at startup/unlock; then `enable_read_guard()` permanently.
  - All reads go through InMemoryStore; v2 code performs zero DB reads at runtime.
- Simple view builder that walks the store to produce `structure` + `notes` + `locks` + `updateUUID` + `version`.
- API: `POST /api2/notes/view` (payload shape compatible with client).

## Data Model and Indexes (500k‑ready)
- Core maps
  - `notes_by_id: Dict[str, Note]` – full decrypted note records.
  - `children_links: Dict[parent_id|None, Dict[id, {prev, next}]]` – adjacency for O(1) re‑links.
  - `head/tail per parent` – constant‑time boundary access.
- Search index (optional feature flag)
  - `inverted_index: Dict[token, Set[id]]` built at hydrate; update on edits.
  - Tokenization: simple normalized terms; configurable stopwords; bounded per‑note postings.
  - Queries resolve to candidate sets; final filter by structure flags; avoids O(N) scans.
- Integrity guards
  - Assertions in mutation paths to keep prev/next/parent relationships consistent; fail‑fast.

## Startup/Unlock Flow
1) Open sqlite (WAL), create schema, read all notes once.
2) If encryption enabled but locked: hold startup with minimal state, or defer hydrate until first successful unlock.
3) Decrypt into InMemoryStore (+ build indexes). Measure timings by 1k batches.
4) Enable read guard.
5) Health check asserts: store.loaded, counts match DB rowcount.

## Request Lifecycle
- V2 dependency provides `UnitOfWork` and access to the singleton store and Undo manager.
- Handler builds Commands → `plan()` + `apply_preview()` → `commit()`.
- Commit stages: coalesce ops → emit batch SQL → single DB transaction → apply to store → push inverse commands.
- Errors crash immediately (no soft fallbacks); no store mutations on failure.

## WriteBatch and Command Design
Operations captured
- note_create(note_id, parent_id, prev_id, next_id, plaintext)
- note_update_content(note_id, plaintext)
- link_update(note_id, parent_id?, prev_id?, next_id?, is_collapsed?)
- note_delete_many(note_ids)

Execution
- Content encryption deferred to commit time (ensures consistent DEK use).
- Coalesce redundant updates (last‑writer‑wins in batch).
- Build `executemany` payloads for homogeneous ops.
- Single transaction boundary via sqlite.

Memory update strategy
- Stage in a local “preview” overlay; apply to InMemoryStore only after DB commit.
- If commit fails, drop overlay; store remains consistent.

## Undo/Redo Semantics
- Snapshot source: InMemoryStore snapshot before/after.
- Diffing: id set diff + record field dict compare.
- Context resets: `TransactionManager.check_context_change()` on search string, client change, or explicit clear.
- Limits: configurable max stack depth; truncation on new branch.

## Endpoint (Phase 0)
- POST `/api2/notes/view` only.

Notes
- No Optional fields in request models; use empty string for “none” where applicable (e.g., `search_context`).
- Handlers construct an ordered Command list, return dev trace (flag‑gated) with `describe()` per command.

## Performance Plan (500k notes)
Bench harness
- Generator script to populate 500k synthetic notes (flat and nested patterns).
- Timed scenarios: initial hydrate; update 1% random edits; move subtree; delete subtree; search queries (top‑K tokens).

Expected complexity and targets
- Hydrate: O(N) linear read/decrypt; goal < 60s on 500k.
- Single edit/move: O(1) store + O(1..log N) per index; commit < 5ms 95p (CPU bound).
- Delete subtree size K: O(K) store; single batched DELETE; ensure no per‑node DB roundtrips.
- Search (token match): O(|postings|) set ops; avoid scanning all notes.

## Rollout (Reset)
Phase 0 – View only
- Scaffold `server_v2/` with: minimal store, view builder, router.
- Hydrate store at startup using existing prefetched rows; enable read guard.
- Implement `POST /api2/notes/view` (structure, notes, locks, updateUUID, version).
- Do NOT touch v1. Do NOT modify client for now.
- Verify with curl/Postman; logs should show `/api2/notes/view`.

Next steps (after view works)
- Add `POST /api2/notes/check-updates`, `acquire-lock`, `release-lock` (in‑memory only).
- Only then start mutations (create/update/delete) using command list + single atomic commit.

## Testing Strategy
- Unit tests
  - Store invariants on inserts/moves/deletes; parent/prev/next cycles rejected.
  - WriteBatch coalescing and commit ordering.
  - Undo/redo deltas restore exact states.
- Property/fuzz
  - Random sequences of moves/edits/deletes; assert equivalence vs. a simple model.
- Integration
  - Endpoints with real UoW; ensure zero DB reads post‑startup (guard violations crash tests).
- Performance
  - Synthetic 500k dataset; stable wall‑clock thresholds; CI smoke with reduced sizes.

## Risks and Mitigations
- Memory footprint at 500k: measure; compact data classes; consider `__slots__`; indexing trade‑offs.
- Encryption key lifecycle: hydrate only after unlock; securely clear keys on logout; re‑hydrate on re‑login.
- Long‑running requests: transaction mutex contention; consider per‑parent sharding if needed later.
- Consistency drift: only apply store updates after DB commit; assert rowcounts on batched ops.

## Acceptance Criteria
- Round 1 (Insert/Delete):
  - Endpoints work end‑to‑end with Undo/Redo using inverse Commands.
  - Single atomic DB transaction per request; commands are inspectible in dev trace.
  - No DB reads after hydrate; read guard enforced.
- Global:
  - InMemoryStore is authoritative and consistent across operations.
  - 500k notes OK under targets; steady‑state ops avoid O(N) scans.

## Implementation Checklist (phase 0)
- [ ] Create `server_v2/` skeleton: store (read‑only), view builder, router.
- [ ] Hydrate store at startup from prefetched rows; enable read guard.
- [ ] Implement `POST /api2/notes/view` (client‑compatible payload).
- [ ] Validate with curl; ensure zero post‑startup DB reads.

## Done (Phase 1a): Update Content + Undo/Redo
- Implement `CmdUpdateContent` in `server_v2/endpoints/update_content.py`:
  - Accept: `clientId`, `noteId`, `content` (required strings)
  - Command builds a single batched SQL update (ciphertext + nonce + tag) and applies new plaintext to `store` only after commit
  - Fail fast for missing note, invalid types; no coercion
  - Zero DB reads at runtime
✅ Wired endpoints: `PUT /api2/notes/{note_id}` and `/api2/notes/{note_id}/save` → `CmdUpdateContent`
✅ Minimal Undo/Redo for content only via `/api2/notes/undo|redo` (empty search context allowed)
✅ No DB reads post‑startup

## Next Step (Phase 1b): View Windowing + Infinite Scroll
- Server windowing: send only first N roots (default 100) and expand window on demand
  - Implemented in `server_v2/snapshot.py` with chunk + buffer; honors `clientSeenRootIds` and `clientNoteUuidHashes`
  - Filter notes payloads to only changed hashes
- Verify client scroll triggers additional `/api2/notes/view` calls as roots are seen; keep payloads small
- Expose window constants via config if needed after tuning


## File‑Per‑Op Structure (for later phases)
When we add mutations (create/update/delete), keep each operation fully self‑contained in its own module for clarity and debuggability.

Layout (proposed, evolves after Phase 0):
- `server_v2/store.py` – InMemoryStore (authoritative, decrypted; no DB reads post‑startup)
- `server_v2/snapshot.py` – view snapshot builder (structure + notes + locks)
- `server_v2/sync.py` – in‑memory locks + update UUID
- `server_v2/uow.py` – UnitOfWork + SqlEmitter interface (single atomic commit)
- `server_v2/ops/` – one file per operation (all logic local to the op)
  - `create_note.py` – CmdCreateNote (plan/apply/emit SQL/inverse)
  - `update_content.py` – CmdUpdateContent
  - `delete_subtree.py` – CmdDeleteSubtree + CmdRestoreSubtree
  - (later) `relink.py`, `collapse.py`, etc.
- `server_v2/core/` – shared helpers used across ops (pure utilities only)
- `server_v2/app.py` – FastAPI router for `/api2/*`

Op module contract
- Define the command class(es) for the op with: `plan(store)`, `inverse(store)`, `to_sql(sql)`, `apply_store(store)`, and `describe()`.
- Keep decision logic (validation, pointer derivation) inside the op file; use `core/` only for reusable primitives.
- No try/except for internal errors; assert invariants and crash fast.
- Requests use required fields only (no Optional); the router enforces shape.

Why this works
- Isolation: each op is reasoned about in one place.
- Debuggability: step‑through an op’s command list without jumping across files.
- Reuse: shared helpers live in `core/`, not scattered across services.

Estimates
- Phase A+B (scaffold + insert/delete + undo/redo + tests): 1–2 days
- Phase C (move/relink): 1–2 days
- Phase D (update content): 0.5–1 day
- Phase E (optional index + perf harness): 2–4 days
- Total (without optional search): ~3–5 days focused effort
