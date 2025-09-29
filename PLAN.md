# Memory Mode Feature Plan

## Goals
- Provide a "memory" mode activated with the `m` key when idle (not editing/searching).
- Show a modal that cycles through read-only notes from the current search view, highlighting the chosen node and full root context.
- Capture user feedback where "more often" increments a positive counter, "less often" increments a negative counter, and "same" leaves counters untouched.

## Deliverables
- FastAPI `/memory` endpoint that tracks per-note feedback in-memory using Laplace-smoothed counts and returns the next note HTML plus metadata.
- Frontend modal with keyboard shortcut, fetch loop, and buttons wired to the endpoint, reflecting updated stats (pos/neg and derived ratio).
- Styling/UX polish for the modal overlay and highlighted note.

## Task Breakdown
1. **Backend Tracking Updates**
   - Replace score accumulator with `{pos, neg}` counts, initialize unseen notes with `pos = 1, neg = 0` (Laplace smoothing) so ratios stay positive.
   - Treat feedback `+1` as incrementing `pos`, `-1` as incrementing `neg`, and `0` as a no-op.
   - Compute selection ratios as `pos / (pos + neg)`; with smoothing every note starts at 1.0 and adjusts as feedback arrives.
   - Simplify selection logic to use these ratios directly (no softmax); choose the note with highest ratio or weighted by ratio depending on user preference (default: highest ratio for now?).

2. **Candidate Selection Logic**
   - Produce flattened list of `(node, root)` pairs to evaluate each note while keeping rendered context.
   - Decide tie-breaking strategy (e.g., random choice among top ratios) and document behaviour.
   - Continue applying highlight flags so templates render selected note with green outline and read-only state.

3. **API Response & Metadata**
   - Adjust response payload to include `pos`, `neg`, and computed ratio `pos / (pos + neg)` instead of score/count.
   - Ensure Pydantic models serialize aliases correctly (`noteId`, `rootNoteId`, etc.).
   - Maintain existing failure modes (422 for missing search query, 404 when no candidates).

4. **Frontend Modal Adjustments**
   - Update display to show positive/negative counts and ratio.
   - Ensure `Same` button skips sending feedback (or sends `0` and backend ignores it).
   - Preserve loading/error states, abort handling, and modal exit behaviours.

5. **Styling & UX**
   - Keep modal overlay, blur, and highlight styles; adjust header text for new statistics if necessary.

6. **Validation**
   - Manual QA: open modal with different search contexts, press each feedback button, inspect stats updates.
   - Note follow-up for potential persistence layer once logic is finalized.

## Dependencies / Questions
- Confirm selection strategy (highest ratio vs. weighted random by ratio); revisit if behaviour feels repetitive.
- Validate `build_note_tree` output includes collapsed children as needed; if not, consider expanding or tracking collapse state.

