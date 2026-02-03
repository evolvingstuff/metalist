# PLAN

## Goal
- Add tag suggestions in the tag bar with co-occurrence + content matches, honoring inheritance/ontology rules and prefix behavior, plus dynamic up/down placement.

## Assumptions
- Suggestions are tag-only and exclude `@` meta tags.
- Content matches must strictly precede co-occurrence suggestions.
- Suggestions show all results (scrollable), no hard cap.
- “Already present” includes explicit tag bar tags, inherited tags, and ontology-implied tags; these are excluded except when matching the current prefix, where they appear at the bottom.
- Content matching uses configurable connector characters (default `-_/.`) to map tags to phrases.
- Client sends current in-editor note content to the server for content-match accuracy.

## Plan
1. Backend suggestions engine
   - Add a tag-suggestions endpoint under `/api2/notes` that accepts `note_id`, current tag-bar context (anchors + prefix), and optional note content (if needed).
   - Extend `SearchIndex` with a helper that takes anchors + prefix and returns co-occurrence-ranked tag candidates (reuse search suggestion scoring).
   - Compute “already present” tags by combining explicit tags, hierarchical inheritance from `NoteStore`, and ontology inference via `TagOntology.infer_effective_tags` (using note plaintext).
   - Compute content matches by normalizing note text and tag terms via configurable connectors; order content matches first, then co-occurrence, then prefix-matched “already present” tags.

2. Client tag-bar suggestion service
   - Add a tag-suggestions service (parallel to `search-suggestions-service.js`) that:
     - Parses tag-bar input around the cursor (wrapper-aware) to derive prefix + replacement range.
     - Sends anchor tags + prefix + note id to the backend.
     - Renders suggestions with mouse + keyboard selection and applies the chosen tag without trailing space.
     - Hides suggestions when tag-bar input is invalid, blurred, or click-away occurs.

3. UI placement + styling
   - Add a suggestions container inside the tag bar.
   - Dynamically position above or below based on available viewport space.
   - Reverse display order when positioned above so the nearest suggestion sits closest to the input.
   - Add CSS (scrollable list, selected state, consistent with search suggestions).

4. Docs + manual test checklist
   - Update `docs/ui/controls.md` and `docs/ui/tag-bar.md` to describe tag suggestions, prefix behavior, and placement.
   - Add a quick manual test checklist for edge cases (inheritance, ontology implication, wrappers, content matches, drop-up).

## Open Questions
- None.

## Test Plan
- Manual:
  - Type in tag bar with existing tags to verify prefix vs space behavior.
  - Confirm content-match tags appear above co-occurrence tags.
  - Verify implied/inherited tags are excluded except for prefix matches (and appear at the bottom).
  - Confirm wrapper tokens and comments behave correctly.
  - Confirm suggestions flip upward near the bottom of the viewport and reverse order visually.

---
After approval, run COMMIT CHECKPOINT to preserve `PLAN.md`.
