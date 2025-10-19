# VDOM Optimization Plan

## Objective
- Reduce unnecessary DOM mutations during note updates so selecting or editing a note only touches the affected elements instead of triggering reorder operations across the tree.

## Current Pain Points to Validate
- `differential-view-service.js` appends every child during each payload, generating redundant "reordered note" logs even when order is unchanged.
- Potential double-work elsewhere (e.g., hash syncing, parent container creation) that may cascade into needless DOM churn.

## Proposed Strategy
1. **Understand Payload Semantics**
   - Confirm how `payload.structure` expresses ordering (likely DFS with `prevId`/`nextId` semantics) and whether stable IDs already match desired DOM positions.
   - Identify cases that truly require reordering: new note creation, move operations, collapse/expand, undo/redo.

2. **Refine DOM Reconciliation**
   - Rework child-order handling per parent: compare desired order with existing DOM siblings and perform minimal moves.
   - Reuse or revise the existing `positionNote` helper (currently unused) so we only move nodes when their parent or adjacent siblings differ.
   - Ensure new elements are inserted once at creation and avoid redundant `appendChild` calls for already correctly placed nodes.

3. **Hash & Content Updates**
   - Double-check content update guard (`shouldUpdateContent`) so editing notes aren't overwritten but non-edited notes still refresh when hashes change.
   - Evaluate whether hash syncing or dataset mutations cause unintended DOM writes; prune any redundant attribute toggles while keeping state accurate.

4. **Safety Nets**
   - Maintain fail-fast behaviour: throw when expected DOM elements are missing, but add targeted assertions to catch logic drift during refactor.
   - Add lightweight instrumentation (counts or debug logs) during development to confirm DOM moves drop significantly; remove or gate them behind existing VDOM logging flag before shipping.

5. **Validation Plan**
   - Manual QA:
     - Select different notes, toggle collapse, create/delete/move notes, undo/redo, and confirm only relevant elements log mutations.
     - Observe real DOM via browser devtools to ensure structure stays correct.
   - Automated checks:
     - Run existing frontend/unit tests (if any) and backend suites to ensure no regressions.

6. **Documentation & Follow-up**
   - Update any developer notes (e.g., `docs/frontend.md` if applicable) describing the leaner diff algorithm and expectations for payload order.
   - Capture open questions for future optimization (e.g., potential virtualization) in TODO or docs once core fix lands.

## Deliverables
- Updated `app/static/js/modules/mode-manager/services/differential-view-service.js` implementing minimal DOM diffing.
- Optional documentation snippet summarizing reconciliation rules.
- Testing notes/results from manual verification.
