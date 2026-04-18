# PLAN

## Feature
- Add a `prioritize` action for the current view with two variants:
  - `prioritize to front`
  - `prioritize to back`
- Input is a single tag token only.
- The action performs a real reorder of stored note order, but only through the currently visible slice of the active view.

## Core Semantics
- Start from the current visible ordering in the active view.
- Partition the visible notes into:
  - notes matching the target tag
  - notes not matching the target tag
- Preserve relative order inside both groups.
- Splice that reordered visible slice back into the full sibling/root order.
- Notes outside the current view keep their relative order.
- Example:
  - Global: `A B C D E`
  - Current view: `B C D`
  - `prioritize to front` for a tag that matches only `D`
  - Resulting stored order: `A D B C E`

## Assumption For V1
- Implement this for root-note ordering in the active filtered/search view first, matching the current server-driven root reorder behavior used by move-to-top.
- If nested per-sibling prioritization is needed later, extend the same stable-partition approach parent-by-parent.

## Implementation Steps
1. Branch setup
- After plan approval, create a feature branch for this work from `main`.

2. Server-side reorder model
- Add a dedicated prioritize use case instead of overloading move-to-top.
- Accept:
  - `tag`
  - `direction` (`front` or `back`)
  - `search_query`
  - existing undo/client/viewport fields
- Validate that the tag is a single non-empty tag token.
- Reuse current search/view scope resolution so the operation is constrained by the active view.

3. Visible-slice reorder algorithm
- Compute the ordered visible roots for the current search context.
- Determine which visible roots match the target tag.
- Build the desired visible order with a stable partition:
  - `front`: matches first
  - `back`: non-matches first
- Apply moves so the stored root order matches that desired visible order once re-spliced into the full root list.
- Treat already-correct order as a no-op.

4. Matching semantics
- Use the same effective tag semantics as search where possible, so prioritization is consistent with how tag-based views are interpreted.
- Do not introduce query parsing beyond a single tag token in V1.

5. API wiring
- Add a notes route for prioritize.
- Return a normal mutation response with update UUID / no-op status.
- Keep the operation fully undoable as one logical command.

6. Client action surface
- Add two explicit actions:
  - `Prioritize tag to front (current view)…`
  - `Prioritize tag to back (current view)…`
- Use a minimal single-tag input flow from the command palette/modal layer.
- Refresh the active view after success and preserve current selection/scroll behavior as much as existing list mutations do.

7. Tests
- Add unit tests for the prioritize use case covering:
  - front partition
  - back partition
  - stable order within matching notes
  - stable order within non-matching notes
  - no-op when already prioritized
  - no-op when no visible notes match
  - filtered-view splice semantics (`A B C D E` + visible `B C D` -> `A D B C E`)
  - invalid tag input
- Add route-level tests for request normalization/validation.
- Run targeted pytest coverage for the new use case and related route tests.

8. Documentation
- Update command/action docs for the new prioritize commands.
- Update any view-order/search docs that need to explain that prioritize mutates stored order through the active view subset.

## Files Likely To Change
- `app/api/routes/notes.py`
- `app/usecases/` (new prioritize command)
- `app/services/snapshot.py` or a small helper near view-scope resolution
- `app/static/js/modules/api-client.js`
- `app/static/js/modules/command-palette/endpoint-registry.js`
- `app/static/config/command_palette_tags.json`
- command-palette/modal client files as needed
- tests under `tests/unit/`
- relevant docs under `docs/ui/`

## Success Criteria
- A user can prioritize one tag to the front or back of the current view.
- The resulting stored order reflects the reordered visible slice.
- Notes outside the current view keep their relative order.
- Matching and non-matching notes each keep their internal order.
- Undo restores the previous order in one step.
- Targeted tests pass.
