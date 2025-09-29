# Memory Mode Feature Plan

## Goals
- Introduce a "memory" study mode triggered by the `m` key when the app is idle (not editing/searching).
- Display a modal that cycles through read-only notes from the current search view, highlighting the targeted node and showing its root context.
- Capture user feedback (-1/0/+1) per note and bias subsequent note selection via a temperature-controlled softmax over note scores.

## Deliverables
- FastAPI `/memory` endpoint that records feedback and returns the next note (HTML) plus metadata.
- In-memory score tracker keyed by note UUID to prototype feedback capture/selection; later swap to persistent storage once flow is validated.
- Frontend modal implementation with keyboard shortcut, fetch loop, and UI for note display + feedback buttons.
- Styling updates for the modal (overlay, background blur, scroll area, highlight styling) and UX polish.

## Task Breakdown
1. **Backend Prototype Layer**
   - Add an in-memory singleton (module-level dict) to track `{note_uuid: {score, count}}` with timestamps for debugging.
   - Provide helper functions to record feedback and fetch current aggregates, ensuring thread safety within the FastAPI process.

2. **Memory Selection Logic**
   - Determine candidate notes for the given search context via `build_note_tree`, flattening to capture individual note IDs plus their root context HTML.
   - Compute score aggregates from the tracker (`sum(outcome)` and `count` per note, defaulting to zero score/zero count when unseen).
   - Apply a numerically stable softmax with a low temperature (≈0.25) over the scores (subtract max before exponentiating) so probabilities naturally converge to uniform when scores are equal.
   - Inject highlight styling (e.g., `memory-highlight` class) into rendered HTML for the selected note and include ratio summaries for display.

3. **API Endpoint**
   - Create request/response Pydantic models covering `searchQuery`, optional `previousNoteId`, and optional `feedback` (-1/0/+1).
   - On each call: optionally record feedback for the prior note, rebuild candidate pool, softmax-select the next note, and respond with HTML + metadata (score, count, average).
   - Ensure fail-fast behavior for invalid inputs (missing search context, unknown UUIDs, etc.).

4. **Frontend Modal Infrastructure**
   - Implement `MemoryModal` extending `BaseModal`, rendering: header (ratio display), scrollable note area (read-only), footer with three feedback buttons.
   - Ensure modal closes via ESC, click-outside, or close icon; cancel pending fetch when closing.
   - Present loading state while waiting for server responses and gracefully handle empty candidate sets.

5. **Keyboard & Mode Integration**
   - Update keyboard handler to open `MemoryModal` on `m` when not editing, not searching, and no other modal active.
   - Track modal state in `ModeContext` as needed (e.g., `modalStack`) to disable conflicting interactions while open.
   - Support continuous loop: button press → POST feedback → display next note until modal exit.

6. **Styling & UX**
   - Add CSS for modal overlay (viewport-sized, blurred backdrop), fixed modal dimensions with internal scrolling, and button row styling.
   - Define `memory-highlight` class for the selected note (e.g., green outline or tinted background) without altering base note layout.
   - Make base page visually blurred/inactive while modal is active.

7. **Validation & Migration Prep**
   - Backend tests for feedback accumulation and softmax weighting (mocked random seed) to guard logic.
   - Manual QA checklist: open modal, ensure note renders, submit each feedback button, verify loop and exit paths.
   - Document follow-up work: replace in-memory tracker with persistent `memory` table (model + migration) once functionality confirmed.

## Dependencies / Open Questions
- Confirm search context string availability on the client; identify how to pass it alongside requests.
- Decide how to clamp/normalize scores before softmax to avoid runaway exponentials (e.g., min/max bounds, optional score decay).
- Evaluate whether `build_note_tree`'s current debug logging needs suppression to keep `/memory` responses lightweight.

