# PLAN: Keep your place when leaving (and entering) edit mode

Branch: `feature/exit-edit-scroll`

## Goal

When you press Escape (or otherwise leave edit mode), the text you were working
on or looking at appears at the same place on screen in the rendered view, as
closely as the format allows, with no visible jump. Where the format makes an
exact match impossible, land close and show a brief cue. Later, the same
mapping runs in reverse when you click into a rendered note to edit it.

## Agreed rules

1. **Anchor choice (leaving edit mode)**
   - Caret on screen → anchor the caret: the same text position stays at the
     same screen height after rendering.
   - Caret off screen (you scrolled away while editing) → anchor what you were
     reading: the note content at the *reading line* (about one third down the
     usable viewport, below the search controls) stays at that height.
   - Neither in the note (e.g. the note is entirely off screen) → keep the
     note's top where it was (no movement).
2. **Note re-collapses on exit** (it was collapsed and you made no edits): its
   content disappears, so keep the collapsed row in view where it was; if it
   would end up above the search controls, place it just below them.
3. **Sorted views** (content volume, updated…): the anchor follows the note even
   if saving re-sorts it; the list reorders around your content.
4. **Clicking a different note while editing:** the clicked spot stays under
   the pointer (same principle, anchor = the click point in the clicked note).
5. **User wins:** any user input (wheel, trackpad, key, pointer down) or user
   scroll ends all pending corrections immediately.
6. **"You are here" cue:** shown only after a *significant* readjustment — the
   anchor could only be mapped approximately, or the view had to move more
   than ~40px from where it was. A faint highlight on the landing block that
   fades in ~600ms; off under reduced-motion; its own on/off option (in a small
   "Visual cues" section of the settings, on by default).

## Phase 1 — Precise anchoring for ordinary notes (fixes the reported bug)

Folds in the uncommitted partial fix on this branch (hold any note by id,
`viewportHold` option on refresh, `getViewportTopInset` export,
`captureExitEditHold`), replacing its "top of note" rule with the rules above.

1. **Capture before exit** (`selection-actions.js`): record the anchor:
   - caret anchor: screen Y of the caret, plus its text position in the note
     (character offset into the note's text and ~30 characters of text on each
     side);
   - reading-line anchor: the same, for the text at the reading line
     (`caretPositionFromPoint` / `caretRangeFromPoint` at the reading line);
   - note-top anchor: note id + top.
2. **Map after render:** find the anchor in the rendered note by the
   surrounding-text match (exact first, then nearest fuzzy match, then the
   character-offset proportion); measure that point's screen Y and scroll by the
   difference. Rich-text notes (the vast majority) map exactly; meta transforms
   (`{{…}}`, link titles) are absorbed by the text match.
3. **Same-frame swap (idea 2):** apply the diff and the anchor correction in the
   same task before the browser paints (no `await` between them), so the
   rendered text appears in place without a one-frame jump. The local
   re-collapse case is corrected in the same frame too.
4. **Stop on user input (idea 7):** the hold's follow-up corrections (and
   resize-driven ones) stop on wheel/touch/key/pointerdown or a user scroll.
5. **Reading line (idea 4):** as defined in rule 1.
6. **Sorted views and switching notes:** rules 3 and 4.
7. **Tests**
   - Browser (`scripts/browser-scroll-regressions.mjs`, Chrome + Firefox in CI):
     long rich-text note — caret visible, caret off screen (reading line), note
     collapsed with/without an edit, expanded with/without an edit, a sorted
     (content-volume) tab, clicking a different note while editing. Each
     asserts the anchored text's screen Y before vs after (±2px) and that no
     intermediate frame showed a jump (sample `requestAnimationFrame` positions
     during the exit).
   - JS unit: the text-anchor matcher (exact, shifted, missing), anchor choice,
     stop-on-input.
   - Confirm each browser case fails on `main` before the fix.

## Phase 2 — Cue and reserved space

1. **"You are here" cue (idea 5):** rule 6; overlay highlight (does not change
   the note's own DOM), threshold logic unit-tested, a new client preference
   (`pref.visual_cues` or similar; allowlisted server-side), a settings toggle.
2. **Reserve space for late content (idea 3)** so later loads don't push the
   text you're reading:
   - inline (data-URI) images: the server knows their pixel size (Pillow) and
     emits `width`/`height` (respecting MetaList image size tags);
   - file-reference images and diagram previews: store/emit known dimensions
     (diagram previews already have sizes; image attachments record theirs on
     upload, older ones measured once and cached);
   - Mermaid (rendered in the browser after the view arrives): reserve the last
     rendered size cached per diagram source for the session;
   - link titles: reserve one line.
   With space reserved, corrections become rare; the correction loop stays as
   a safety net.
3. **Tests:** layout-shift measurement in the browser (anchored text stays put
   while an image/diagram finishes loading); render-output unit tests for the
   emitted dimensions; render-cache tests unchanged in behaviour.

## Phase 3 — Source mapping for formatted notes (idea 1)

1. The server renderer (`content_formatting.py`, `markdown_rendering.py`,
   CSV/JSON/LaTeX renderers) tags rendered blocks with the source range they
   came from (`data-src="start-end"` character offsets into the raw note
   text): Markdown blocks (paragraph, heading, list item, code block, table
   row), CSV rows, JSON lines/keys; LaTeX and Mermaid as one block each
   (proportional within).
2. Leaving edit mode maps the caret's raw-text offset to the block whose
   `data-src` contains it, then to a position inside the block (proportional by
   characters), instead of the Phase 1 text match.
3. Attribute safety: the sanitizer (`note_html.py` policy) must allow `data-src`
   on the relevant elements; render-cache keys and hashes change once (all
   notes re-render once after upgrade).
4. **Tests:** renderer unit tests per format (ranges cover the source, nested
   lists, tables, code fences, invalid input badges); browser cases for a long
   Markdown note and a CSV note (caret mapped to the right block/row).

## Phase 4 — Symmetric mapping when entering edit mode (idea 6)

1. Clicking a rendered note: find the clicked block's `data-src` range and the
   click's position inside it; after the raw editable content arrives, place the
   caret at the corresponding raw-text offset and keep that spot at the click's
   screen height (same-frame, same hold machinery).
2. Rich text: map the click by the Phase 1 text match (rendered ≈ raw).
3. Formats with no sensible caret mapping (Mermaid, LaTeX): place the caret at
   the start of the block's source and keep the block in place.
4. **Tests:** browser cases clicking into the middle of a long Markdown note, a
   CSV row and a rich-text paragraph: caret lands at the matching source spot,
   which stays at the click's height.

## Edge cases (tested across phases)

- Very short notes; notes taller than the viewport; the note at the very top or
  bottom of the loaded band of roots; the band moving during the refresh.
- Empty note; caret at the very start or end; caret inside the tag bar (use the
  reading-line anchor).
- Search views where the note stops matching after the edit (it disappears:
  fall back to keeping the neighbouring note in place).
- Note deleted or locked by another client during the exit.
- Undo right after exit (existing undo scroll logic keeps priority).
- Reduced motion; Drag & Drop/visual-cue preferences off.
- Chrome and Firefox (CI runs both on every OS); Safari not targeted.

## Docs and AI help

`docs/ui/controls.md`, `docs/design/differential-view-protocol.md`,
`docs/testing/harness.md`, AI help skills (`help-notes.md`, `help-menus.md` for
the cue option), `docs/AI-SUMMARY.md`.

## Checkpoints

Commit checkpoint after each phase once you have tested it.
