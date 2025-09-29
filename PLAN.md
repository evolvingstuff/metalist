# Memory Mode Feature Plan

## Goals
- Provide a "memory" mode activated with the `m` key when idle (not editing/searching).
- Surface a modal that cycles through notes from the current search context, highlighting the chosen node plus its ancestor/descendant context.
- Capture user feedback where "More Often" increments a positive counter, "Less Often" increments a negative counter, and "Same" leaves counters untouched.

## Progress Checklist
### Backend
- [x] Track per-note feedback with in-memory `{pos, neg}` counters (Laplace smoothing baked in during ratio calc).
- [x] Normalize ratios to a proper probability mass function and sample using cumulative weights.
- [x] Fail-fast if probability normalization drifts (sanity assertion).
- [x] Collapse non-selected branches while keeping selected node ancestors/descendants expanded in rendered tree.
- [ ] Persist feedback to a database table (temporary in-memory store still resets on restart).
- [ ] Expose debugging endpoint or admin view to inspect aggregated memory stats (optional, pending discussion).

### API / Rendering
- [x] `/api/memory` accepts optional prior note + feedback, records results, and responds with rendered HTML + metadata.
- [x] Response payload now returns `positive`, `negative`, `ratio`, and `probability` using JSON aliases.
- [x] Template renders highlighted note with outline + soft green tint and removes editability.
- [ ] Consider throttling or debouncing repeated requests to avoid rapid-fire fetch loops (investigate once UX reviewed).

### Frontend Modal
- [x] Keyboard shortcut (`m`) launches modal when idle; ESC/click-outside close it.
- [x] Top-aligned feedback buttons with disabled state while requests are in-flight.
- [x] Footer displays `Less`/`More` counts and actual selection probability.
- [x] Auto-scroll keeps highlighted note in view on each response.
- [x] Selected note shown read-only with contextual tree, unrelated branches collapsed for focus.
- [ ] Add loading/error messaging polish (e.g., retry CTA) and maybe keyboard shortcuts for buttons.

### Styling & UX
- [x] Modal overlay blurs background, prevents interaction, and highlights selected note with outline+tint.
- [ ] Evaluate accessibility contrast/ARIA labels for controls (pending audit).

### Validation & Follow-ups
- [x] Manual smoke testing in browser.
- [ ] Add automated backend tests covering probability normalization and branch collapsing logic.
- [ ] Document manual QA steps and potential future DB migration (README / docs entry).
- [ ] Future: swap in-memory tracker for persistent `memory` table + migrations once model is finalized.

## Open Questions / Next Steps
- What cadence should trigger the eventual database-backed implementation? (Need schema + migration plan.)
- Should the modal surface additional context (e.g., note path breadcrumbs) or remain minimal?
- Do we need rate limiting or a cooldown timer between memory selections?
- When we move to persistence, should we prune very old feedback or keep full history?

