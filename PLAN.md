# Performance Investigation Plan

## Goal
Identify and prioritize the factors making note operations sluggish after seeding with large lorem dataset. Deliver actionable recommendations (and possible quick wins) for making the app feel lightning fast.

## Steps
1. **Baseline Measurements**
   - Capture end-to-end timings for common interactions (load, create, update, move, delete) using existing dev APIs or UI tooling.
   - Record server-side timings/logs and note client-side rendering duration if observable.

2. **Server Profiling & Logging Review**
   - Inspect FastAPI middleware/logs for per-request timing and payload sizes.
   - Review `NoteService` / linked list operations (including integrity checks) for hot paths.
   - Confirm whether responses send full tree vs. diffs and measure payload size.

3. **Database Analysis**
   - Measure query counts and execution time for representative operations using SQLAlchemy instrumentation.
   - Check index coverage and potential N+1 patterns.
   - Evaluate cost of integrity checks and cache updates.

4. **Client Sync Flow Evaluation**
   - Examine `/api/notes/check-updates`, sync UUID churn, and how delta vs. full payloads are handled.
   - Evaluate state-tracking strategies (e.g., per-note hashes / queryable deltas, server-held snapshots) to enable thin diff responses; avoid event-log approach for now.
   - Trace clipboard/lock management for potential bottlenecks.

5. **Integrity & Dev-Mode Overheads**
   - Audit dev-only checks, assertions, and logging for runtime impact.
   - Experimentally toggle heavyweight checks (if safe) to quantify effect.

6. **Opportunity Matrix**
   - Summarize findings with estimated impact vs. implementation effort.
   - Recommend next actions (e.g., diff-based responses, caching adjustments, integrity gating, async tasks).
