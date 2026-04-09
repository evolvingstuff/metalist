# Testing Coverage Plan

## Current Decision

As of 2026-04-08, Cypress is being removed from the repo.

Reason:

- it has not provided enough value relative to the maintenance/debugging cost
- too many failures were about shared timing/focus/event-pipeline behavior
- the suite was not a trusted green baseline

If browser automation returns later, it should return only as a very small
smoke suite on top of stronger lower-level coverage.

## Goal

Make automated testing useful again by:

- keeping browser automation optional and minimal
- moving shared interaction logic coverage below Cypress
- defining what "baseline" means for this repo
- stopping the pattern where one event-pipeline change splashes failures across unrelated UI specs

## Problem Statement

Recent debugging exposed a mismatch between what the Cypress suite appears to test and what it actually tests.

At the spec level, Cypress tests are isolated in data:

- `POST /api2/test/reset` clears server state in `TEST_MODE`
- `cy.resetTestState()` clears browser storage
- `cy.visitApp('/')` waits for the app-ready boundary

But many specs still depend on the same shared client interaction core:

- `app/static/js/modules/mode-manager/events/mouse-events.js`
- `app/static/js/modules/mode-manager/events/keyboard-events.js`
- `app/static/js/modules/mode-manager/actions/selection-actions.js`
- `app/static/js/modules/mode-manager/actions/history-actions.js`
- `app/static/js/modules/mode-manager/actions/ui-actions.js`
- `app/static/js/modules/mode-manager/services/command-gate-service.js`
- `app/static/js/modules/mode-manager/mode-context.js`

That means a broad fix in click handling, loading gates, focus routing, shortcut replay, or edit-mode transitions can move multiple Cypress specs even when the user-facing feature under test looks unrelated.

Example:

- `cypress/e2e/collapsed_image_preview_thumbnail.cy.js` is nominally about collapsed image thumbnails
- but it still depends on the shared collapse/edit/click state machine
- so a change in the global mouse/loading path can break it without changing thumbnail rendering at all

## Working Hypothesis

The pain we observed was:

1. too much shared behavior is only tested at the browser integration layer
2. the full Cypress suite is being used as a first-line debugging tool instead of a thin integration net
3. we do not have a clearly documented baseline for what test result set counts as normal
4. some specs are broader than their names imply, which makes failures harder to interpret

## What The Baseline Should Mean

A baseline should answer one question:

"Does the core note interaction state machine still work?"

It should not try to answer:

"Does every UI behavior in the product still work?"

### Baseline Definition

A useful baseline is:

- one commit SHA
- one explicit command set
- one expected result set
- if not fully green, one allowlist of known failures

Without that, every failure is ambiguous:

- pre-existing failure
- flaky failure
- regression from current work

## What The Baseline Should Actually Test

The baseline should focus on the shared interaction contract.

### Browser-Level Smoke Coverage

If browser automation is reintroduced, keep only a small smoke suite for flows
that truly need a real browser:

1. app boot and ready boundary
2. create root note
3. create child note
4. select note and switch note
5. collapse parent note
6. click collapsed note and auto-expand into edit mode
7. delete selected note
8. undo / redo around delete and selection restore
9. search input focus and "create from search"
10. one tag-bar or focus-transfer smoke path if that is considered core

Candidate flows to keep, rewrite, or replace as smoke coverage:

- `cypress/e2e/search_enter_creates_note.cy.js`
- `cypress/e2e/undo_selecting_collapsed_note_is_single_undo.cy.js`
- `cypress/e2e/undo_delete_selection_restores_previous_note.cy.js`
- `cypress/e2e/undo_delete_switch_restores_previous_selection.cy.js`
- `cypress/e2e/undo_deselect_restores_none_selected.cy.js`
- `cypress/e2e/expand_toggle_visible_for_collapsed_parents.cy.js`
- `cypress/e2e/tag_bar_cmd_enter_creates_notes.cy.js` if tag-bar focus is core

Target size: roughly 5 to 8 specs, not 20+.

## What Should Move Below Cypress

Browser automation should not be the main place where we discover regressions in shared event-routing logic.

### Add Or Expand JS Unit Tests For

- keyboard shortcut gating and input filtering
  - `keyboard-events.js`
- click-target routing and note-selection targeting
  - `mouse-events.js`
  - `note_click_target_service.test.mjs`
- collapse/edit-session policy
  - `edit_session_collapse_policy_service.test.mjs`
- filtered refresh and selection restoration
  - `ui_actions_filtered_refresh_selection.test.mjs`
- command gate busy/loading behavior
  - `command-gate-service.js`
- search-focus and clipboard shortcut policies
  - `clipboard_shortcut_policy_service.test.mjs`

### Add Or Expand Python Tests For

- undo stack focus-target rules
  - `tests/unit/test_undo_state_focus_note_id.py`
- delete snapshot correctness
  - `tests/unit/test_delete_subtree_snapshot.py`
- edit-mode coalescing and collapse restoration
  - `tests/unit/test_undo_state_edit_mode_coalescing.py`

These lower-level tests should answer:

- when does a click select vs no-op vs deselect
- when are shortcuts dropped vs ignored vs allowed
- what focus note should undo/redo restore
- when should a collapsed note auto-expand and when should collapse be restored

## How Browser Automation Should Be Used

### Keep It For

- real browser focus behavior
- DOM event ordering
- contenteditable behavior
- shortcut transport through the browser
- final end-to-end confidence on core flows

### Do Not Use It As The First Tool For

- debugging shared interaction rules
- validating pure decision logic
- proving focus-target computation
- proving undo-stack semantics that can be tested directly

## Proposed Suite Split

### 1. Smoke Suite

Purpose:

- fast regression signal for the core note state machine

Run:

- on feature completion
- before merge
- possibly on every PR if it stays small and stable

### 2. Extended Browser Suite

Purpose:

- feature-level browser coverage for less central flows

Examples:

- collapsed preview rendering
- command palette details
- search redaction edge cases
- paste + inheritance edge cases
- specialized tag-bar flows

Run:

- nightly
- on-demand
- before larger UI merges

### 3. Lower-Level Test Suites

Purpose:

- catch shared-logic regressions cheaply and deterministically

Run:

- continuously during development
- as the primary debugging loop

## Design Rules Going Forward

1. Do not patch the global event pipeline to fix a single browser spec unless the failure is clearly a shared-interaction bug.
2. If a browser failure points at selection, loading, collapse, or shortcut routing, first reproduce it in a lower-level test if possible.
3. If a spec's name hides a broader dependency on shared interaction logic, rewrite or rename it.
4. The smoke suite should only contain flows we are willing to treat as merge-blocking for most UI work.
5. The extended suite can be noisy without blocking small changes, as long as the noise is tracked and intentionally bounded.

## Immediate Next Steps

1. Cypress was removed. If browser automation returns, classify each spec as `smoke`, `extended`, `rewrite`, or `delete`.
2. Add missing JS unit tests around shared click/keyboard/loading decision logic.
3. Add targeted undo/collapse tests at the Python and JS layers before changing more shared handlers.
4. Define one recorded baseline commit and its expected results.
5. Update `docs/testing/harness.md` once the new split is decided.

## Success Criteria

This plan is working if:

- a small UI change usually requires rerunning only unit tests plus a tiny smoke suite
- a failure in an "unrelated" browser spec becomes rare
- most shared interaction regressions are caught below the browser layer
- any future full browser run becomes a confidence run, not the main debugging loop
