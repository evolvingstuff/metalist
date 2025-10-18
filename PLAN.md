# Investigation Plan: DB Cache Corruption

## Goal
Identify the root cause of the cache corruption that triggers `CACHE CORRUPTION: Note f22c2495-c1e6-4c85-9e55-6b8ee9496e96 not found in cache` when loading `/api/notes/view`.

## Steps
1. **Establish Baseline & Safeguards**
   - Back up the current `notes.db` to preserve the corrupted state.
   - Gather top-level DB metadata (table counts, schema) so we know what data exists.

2. **Targeted Reproduction & Telemetry Capture**
   - Reproduce the failure via the API to confirm it is deterministic.
   - Capture detailed logs (middleware + renderer + cache) for the failing request.

3. **Code Path & Invariant Review**
   - Trace how the note cache is built: `content_cache`, `LinkedListManager`, and `build_note_tree`.
   - Document required invariants (cache population order, expected note/link records).

4. **Database Integrity Inspection**
   - Inspect DB rows referencing `f22c2495-c1e6-4c85-9e55-6b8ee9496e96` (notes, linked list pointers, cache tables, undo history).
   - Check for orphaned references, inconsistent parent/prev/next pointers, or cache entries missing source notes.

5. **Root Cause Hypothesis & Validation**
   - Form hypotheses explaining how the cache lost the note while linked list still references it.
   - Validate by correlating data anomalies with code logic (e.g., missing transactional protection, cache eviction bugs).
   - Produce a written root-cause report with evidence and remediation recommendations (code fixes, data repair steps).

## Deliverables
- Investigation notes with findings per step.
- Root cause analysis document summarizing evidence, hypothesis, and mitigation recommendations.
