# Server V2 Rewrite Plan: Greenfield, Command‑Driven, and Scalable

Owner: server/platform
Status: Proposal – awaiting approval
Scope: New greenfield server in `server_v2/` mounted alongside current app; frontend/static remains unchanged

## Goals
- Single read of sqlite3 at startup/unlock; forbid all post‑startup DB reads.
- All data kept decrypted in memory; encrypt only at rest.
- Every API request builds an explicit, inspectible list of Commands.
- Commands serve both Undo/Redo and batched SQL writes within a single atomic transaction.
- Scale comfortably to 500k notes; avoid O(N) operations in steady state.
- Undo/Redo resets on context boundaries (e.g., search changes, client switch).

Non‑goals
- Multi‑user sync or remote collaboration.
- Cross‑process shared in‑memory state.

## Baseline (what to keep vs. replace)
Keep (only what’s strictly needed)
- Encryption primitives (DEK/AES‑GCM): `app/services/encryption.py` and compat in `app/utils/encryption.py`.

Replace (greenfield for everything else)
- API surface, services, store, transaction flow, and DB helpers: implemented fresh under `server_v2/`.
- Eliminate all runtime `allow_reads` fallbacks; v2 does not read DB after hydrate.

## Architecture Overview (Server V2)
- InMemoryStore (authoritative)
  - Unified decrypted record per note: content + parent/prev/next + flags + timestamps.
  - O(1) by‑id; O(1) head/tail/sibling navigation; RLock‑guarded.
  - Optional inverted index for search (later phase).
- Strict DB Access Policy
  - Hydrate once at startup/unlock; then `enable_read_guard()` permanently.
  - All reads go through InMemoryStore; v2 code performs zero DB reads at runtime.
- Command Pattern + UnitOfWork
  - Handlers build an ordered list of Commands (inspectible, typed, debuggable).
  - `plan(store)` validates invariants; `apply_preview(store_overlay)` produces inverse Commands.
  - `to_sql()` emits compact, batchable ops; `UnitOfWork.commit()` executes once inside a transaction.
  - On success: apply overlay to InMemoryStore and push inverse list to Undo stack.
  - On failure: rollback; store remains unchanged.
- Undo/Redo Integration
  - Inverse Commands maintained per client; resets on search/client boundaries or explicit clear.
  - No DB reads; deltas come from the store.

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

## V2 Endpoints (Round 1)
- POST `/api2/notes/insert` – create note (required fields: `client_id`, `parent_id`, `prev_id`, `content`).
- POST `/api2/notes/delete` – delete subtree (required: `client_id`, `note_id`).
- POST `/api2/undo` – undo last for client (required: `client_id`, `search_context`).
- POST `/api2/redo` – redo last for client (required: `client_id`, `search_context`).

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

## Migration and Rollout (Small, verifiable steps)
Phase A – Scaffold v2 (day 0.5)
- Create `server_v2/` with app bootstrap, store skeleton, Command base, UnitOfWork, undo manager.
- Mount router at `/api2` without touching existing client/static.

Phase B – Insert/Delete MVP (1–2 days)
- Implement Commands: `CmdCreateNote`, `CmdDeleteSubtree` + their inverse commands.
- Finish store invariants; batch SQL for insert/delete; atomic commit.
- Implement `/api2/notes/insert`, `/api2/notes/delete`, `/api2/undo`, `/api2/redo`.
- Tests: end‑to‑end undo/redo for insert/delete, fuzz for cycles, zero DB reads after hydrate.

Phase C – Move/Relink (1–2 days)
- Add `Relink` command (move), update adjacency; batch link updates.
- Undo/redo coverage and performance checks.

Phase D – Update Content (0.5–1 day)
- Add `UpdateContent` command; encrypt at commit; update search index if enabled.

Phase E – Optional search index + perf harness (2–4 days)
- Build inverted index; flag‑gated integration; bench on large datasets.

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

## Implementation Checklist (high‑level)
- [ ] Scaffold `server_v2/` and router `/api2`.
- [ ] Implement InMemoryStore skeleton and hydration.
- [ ] Implement Command base + UnitOfWork (with trace mode).
- [ ] Implement CmdCreateNote/CmdDeleteSubtree + inverse commands.
- [ ] Implement `/api2/notes/insert`, `/api2/notes/delete`, `/api2/undo`, `/api2/redo`.
- [ ] Enforce read guard; remove any DB reads from v2 runtime.
- [ ] Tests (insert/delete + undo/redo; invariants; zero post‑startup reads).
- [ ] Next: Relink, UpdateContent, optional search index.

Estimates
- Phase A+B (scaffold + insert/delete + undo/redo + tests): 1–2 days
- Phase C (move/relink): 1–2 days
- Phase D (update content): 0.5–1 day
- Phase E (optional index + perf harness): 2–4 days
- Total (without optional search): ~3–5 days focused effort
