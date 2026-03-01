# PLAN: Embedded Note References + Cmd+R Insert

## Goal
Implement embedded note references so `![[UUID]]` inside a note renders the referenced note subtree in view mode, and add an editing shortcut (`Cmd/Ctrl+R`) that inserts `![[UUID]]` from the last copied note UUID.

## Scope (This Feature)
1. View-mode embed rendering for `![[UUID]]`.
2. Embeds render as block-level content on their own visual line even when token appears inline with surrounding text.
3. Recursive subtree render for embedded note (include children regardless of collapsed state).
4. Missing-reference visual state when UUID does not exist.
5. Circular-reference visual state when recursion would cycle; stop recursion at that point.
6. Embedded-note styling (light tinted background, no collapse arrows/affordances).
7. Editing behavior unchanged for embeds: raw `![[UUID]]` remains visible while editing.
8. Keyboard shortcut: in edit mode, `Cmd/Ctrl+R` inserts `![[UUID]]` at caret using UUID from note-copy flow.
9. Keep search semantics unchanged: referenced note tags do not affect search matches for host note.

## Out of Scope
1. Plain links `[[UUID]]` without `!` (deferred).
2. Backlinks/jump-to-note UI.
3. File references or attachment graph features.

## Implementation Plan
1. Server-side embedded render pipeline
   - Add embed-reference parsing and rendering in view-only rendering path.
   - Parse only `![[UUID]]` tokens from text segments (not inside HTML tags/attributes).
   - Normalize render output so each embed token is emitted as a block node with line breaks before/after in view mode (inline `blah ![[UUID]] yada` renders visually as three lines: `blah`, embed block, `yada`).
   - Render embeds recursively from `note_store` so referenced note + descendants are emitted as static embed HTML blocks.
   - Keep host note raw content unchanged when `flags.isEditing` is true.

2. Recursion safety + failure states
   - Track traversal stack for embed expansion.
   - If referenced UUID is missing: render a compact “missing/broken reference” indicator with icon + UUID context.
   - If referenced UUID is already on stack: render a compact “circular reference” indicator with circle-arrow icon, do not recurse further.

3. Hash + diff correctness
   - Ensure rendered embed HTML is part of note payload content before hashing.
   - Confirm that changes in referenced note content/tags/children update host note hash so `/api2/notes/view` diffs refresh host note render.
   - Keep search index logic unchanged (no embed-tag contribution to host note search behavior).

4. Styling
   - Add CSS classes for embedded containers/content/children and error-cycle markers.
   - Apply light grey-ish tint and subtle border/padding.
   - Ensure embedded subtree visually nests without using `.note` containers (so no arrows/interactive affordances).

5. Copy flow + shortcut plumbing (`Cmd/Ctrl+R`)
   - Extend copy response payload to include copied root `note_id`.
   - On successful note-copy shortcut, store copied UUID in `ModeContext` clipboard note state.
   - Add keyboard handler for `Cmd/Ctrl+R` (editing mode only) that inserts `![[<clipboardNoteId>]]` at caret.
   - If no copied note UUID is available, treat as no-op (log-only, no crash).

6. UI/docs alignment
   - Update shortcut docs (`docs/ui/controls.md`) to include `Cmd/Ctrl+R`.
   - Update formatting docs (`docs/ui/content-formatting.md`) with embed syntax and view/edit behavior.
   - Update help modal shortcut list to include reference insertion.

7. Tests
   - Python unit tests:
     - Embed rendering of existing note + descendants.
     - Missing UUID marker rendering.
     - Circular reference marker + recursion stop.
     - Non-editing vs editing behavior for raw token visibility.
     - Host hash changes when embedded target content changes.
   - JS unit test(s) for keyboard shortcut insertion behavior (or focused Cypress if unit harness is insufficient).
   - Run targeted tests and `./sanitycheck/run`.

## Success Criteria
1. In view mode, `![[UUID]]` renders referenced note subtree with tinted embed styling.
2. Inline embed tokens still render as standalone block lines in view mode.
3. In edit mode, user sees and edits raw `![[UUID]]` text (no rendered embed replacement).
4. Missing UUID renders a broken-reference indicator; cycles render a circular-reference indicator and stop expansion.
5. Embedded render ignores source note collapse state and shows no collapse affordances.
6. `Cmd/Ctrl+R` inserts `![[UUID]]` for the most recently note-copied UUID while editing.
7. Search behavior is unchanged: referenced note tags do not influence host note search results.

## Risks / Watchouts
1. Wrapper syntax overlap with `[[...]]`: embed token parsing must avoid accidental consumption by existing wrapper formatting.
2. Hash churn/perf: recursive rendering must be deterministic and bounded.
3. Cursor insertion edge cases in contenteditable can be browser-sensitive; include fallback insertion path.

## Docs Gap Noted
No dedicated doc currently exists for note references/embeds. Proposal: keep docs concise by updating `docs/ui/content-formatting.md` and `docs/ui/controls.md` in this feature; split to `docs/ui/references.md` later only if scope grows.
