// Keeps what the user is looking at still while the page changes under it:
// view diffs adding or removing roots above the viewport (the loaded band of
// roots moving), or a note leaving edit mode (re-rendering, re-collapsing).
//
// A hold anchors either a text position inside a note ("text": the caret, or
// the line the user was reading) or a note's top edge ("top"). While a hold is
// active, every layout change of the notes container is corrected from a
// ResizeObserver callback, which runs after layout and before paint, so the
// anchored text never visibly jumps. The browser's own scroll anchoring is
// switched off meanwhile so the two never fight. The hold ends on any user
// input or scroll, once the layout has been still for a moment, or after a
// maximum time.

import { ApplicationState } from '../../application-state.js';
import { getViewportTopInset } from './scroll-restoration-service.js';

// How much of a kept-visible note must remain below the search controls.
const MIN_VISIBLE_PX = 24;
const QUIET_MS = 700;
const MAX_HOLD_MS = 4000;
// Characters of context recorded on each side of an anchored text position.
const CONTEXT_CHARS = 30;
const USER_INPUT_EVENTS = ['wheel', 'touchstart', 'keydown', 'mousedown', 'pointerdown'];
// A "you are here" cue follows a hold only when the user's place had to move
// this far, or could only be found approximately.
const CUE_MIN_MOVE_PX = 40;
const CUE_DURATION_MS = 600;

const moduleState = ApplicationState.createFields('viewport-hold-service', {
    session: null,
    // The cue shown for a hold reference; a hold restarted with the same
    // reference (the refresh after saving re-holds it) keeps this cue.
    lastCue: null,
});

// A note being edited keeps its `collapsed` class but shows its content.
function isShownCollapsed(element) {
    return element.classList.contains('collapsed') && !element.classList.contains('editing');
}

function notesContainer() {
    const container = document.getElementById('notes-container');
    if (!container) {
        throw new Error('notes-container not found');
    }
    return container;
}

function findNoteElement(noteId) {
    return notesContainer().querySelector(`.note[data-note-id="${CSS.escape(noteId)}"]`);
}

function noteContent(noteElement) {
    const content = noteElement.querySelector(':scope > .note-content');
    if (!(content instanceof HTMLElement)) {
        throw new Error(`Note ${noteElement.dataset.noteId} has no content element`);
    }
    return content;
}

export function captureViewportRoot() {
    for (const element of notesContainer().querySelectorAll(':scope > .note[data-note-id]')) {
        const rect = element.getBoundingClientRect();
        if (rect.bottom > 0) {
            return { kind: 'top', noteId: element.dataset.noteId, top: rect.top, keepVisible: false };
        }
    }
    return null;
}

// --- Text positions -------------------------------------------------------

function textOffsetOf(content, node, offset) {
    const range = document.createRange();
    range.setStart(content, 0);
    range.setEnd(node, offset);
    return range.toString().length;
}

// Screen Y of the character position `position` in content's text, or null.
function textPositionToY(content, position) {
    const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    let consumed = 0;
    let node = walker.nextNode();
    while (node !== null) {
        const length = node.data.length;
        if (consumed + length >= position) {
            const range = document.createRange();
            range.setStart(node, position - consumed);
            range.collapse(true);
            const rects = range.getClientRects();
            if (rects.length > 0) {
                return rects[0].top;
            }
            const parentRect = node.parentElement.getBoundingClientRect();
            return parentRect.height > 0 ? parentRect.top : null;
        }
        consumed += length;
        node = walker.nextNode();
    }
    return null;
}

// Where an anchored text position is in `text` (the note's text after it
// re-rendered): the surrounding text matched nearest to the old offset, or,
// when the text changed shape, the same proportion of the way through.
// `exact` is false when only an approximate position could be found.
export function findTextPosition(text, anchor) {
    if (typeof text !== 'string') {
        throw new Error('findTextPosition requires text');
    }
    const nearest = (needle, shift) => {
        if (needle.length === 0) {
            return null;
        }
        let best = null;
        let index = text.indexOf(needle);
        while (index !== -1) {
            const position = index + shift;
            if (best === null || Math.abs(position - anchor.textOffset) < Math.abs(best - anchor.textOffset)) {
                best = position;
            }
            index = text.indexOf(needle, index + 1);
        }
        return best;
    };
    const trimmedBefore = anchor.before.trimEnd();
    for (const [needle, shift] of [
        [anchor.before + anchor.after, anchor.before.length],
        // Rendering can drop whitespace the user just typed next to the caret.
        [trimmedBefore + anchor.after.trimStart(), trimmedBefore.length],
        [trimmedBefore, trimmedBefore.length],
        [anchor.after.trimStart(), 0],
    ]) {
        // Short fragments match too easily to count as the same place.
        if (needle.length < 8) {
            continue;
        }
        const position = nearest(needle, shift);
        if (position !== null) {
            return { position, exact: true };
        }
    }
    const proportional = Math.round(anchor.textOffset * text.length / Math.max(1, anchor.textLength));
    return { position: Math.min(text.length, Math.max(0, proportional)), exact: false };
}

function caretPositionAt(x, y) {
    if (typeof document.caretPositionFromPoint === 'function') {
        const position = document.caretPositionFromPoint(x, y);
        return position === null ? null : { node: position.offsetNode, offset: position.offset };
    }
    if (typeof document.caretRangeFromPoint === 'function') {
        const range = document.caretRangeFromPoint(x, y);
        return range === null ? null : { node: range.startContainer, offset: range.startOffset };
    }
    return null;
}

// What to keep in place when this note leaves edit mode: the caret if it is
// on screen, otherwise the text at the reading line (a third of the way down
// the usable viewport), otherwise the note's top. `keepVisible` keeps a note
// that collapses or shrinks in view.
export function captureNoteAnchor(noteElement) {
    const noteId = noteElement.dataset.noteId;
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('captureNoteAnchor requires a note element with an id');
    }
    const content = noteContent(noteElement);
    const noteTop = noteElement.getBoundingClientRect().top;
    const inset = getViewportTopInset();
    const viewportBottom = window.innerHeight;
    const textAnchorAt = (node, offset) => {
        const text = content.textContent;
        const textOffset = textOffsetOf(content, node, offset);
        const screenY = textPositionToY(content, textOffset);
        if (screenY === null) {
            return null;
        }
        return {
            kind: 'text', noteId, screenY, textOffset, textLength: text.length,
            before: text.slice(Math.max(0, textOffset - CONTEXT_CHARS), textOffset),
            after: text.slice(textOffset, textOffset + CONTEXT_CHARS),
            noteTop, keepVisible: true,
        };
    };

    const selection = window.getSelection();
    if (selection !== null && selection.rangeCount > 0 && content.contains(selection.focusNode)) {
        const caret = textAnchorAt(selection.focusNode, selection.focusOffset);
        if (caret !== null && caret.screenY >= inset && caret.screenY <= viewportBottom) {
            return caret;
        }
    }

    const readingLineY = inset + (viewportBottom - inset) / 3;
    const contentRect = content.getBoundingClientRect();
    if (contentRect.top <= readingLineY && contentRect.bottom >= readingLineY) {
        const position = caretPositionAt(contentRect.left + Math.min(40, contentRect.width / 2), readingLineY);
        if (position !== null && content.contains(position.node)) {
            const reading = textAnchorAt(position.node, position.offset);
            if (reading !== null) {
                return reading;
            }
        }
    }

    return { kind: 'top', noteId, top: noteTop, keepVisible: true };
}

// --- Sorted tabs ----------------------------------------------------------

function rootElementOf(noteElement) {
    const container = notesContainer();
    let element = noteElement;
    while (element.parentElement !== container) {
        const parentNote = element.parentElement.closest('.note[data-note-id]');
        if (parentNote === null) {
            throw new Error('Note is not inside a root note of the notes container');
        }
        element = parentNote;
    }
    return element;
}

// The id of the root note right before or after `rootElement`, or null.
function siblingInDirection(element, direction) {
    if (direction === 'previous') {
        return element.previousElementSibling;
    }
    if (direction === 'next') {
        return element.nextElementSibling;
    }
    throw new Error(`Unknown direction: ${direction}`);
}

function adjacentRootId(rootElement, direction) {
    let element = siblingInDirection(rootElement, direction);
    while (element !== null && !element.matches('.note[data-note-id]')) {
        element = siblingInDirection(element, direction);
    }
    if (element === null) {
        return null;
    }
    return element.dataset.noteId;
}

// Leaving edit mode in a sorted tab moves the edited note's root to its sorted
// place. While that root keeps its neighbours, hold the caret/reading-line
// anchor as usual; once it has moved, hold the root that was below it (or
// above, at the end of the list) so the surrounding notes stay on screen.
export function captureSortedExitAnchor(noteElement) {
    const primary = captureNoteAnchor(noteElement);
    const root = rootElementOf(noteElement);
    const previousRootId = adjacentRootId(root, 'previous');
    const nextRootId = adjacentRootId(root, 'next');
    let neighbourId = nextRootId;
    if (neighbourId === null) {
        neighbourId = previousRootId;
    }
    if (neighbourId === null) {
        return primary;
    }
    const neighbourTop = findNoteElement(neighbourId).getBoundingClientRect().top;
    return {
        kind: 'sorted',
        noteId: primary.noteId,
        keepVisible: false,
        primary,
        rootId: root.dataset.noteId,
        previousRootId,
        nextRootId,
        neighbour: { kind: 'top', noteId: neighbourId, top: neighbourTop, keepVisible: false },
    };
}

function sortedRootMoved(reference) {
    const root = findNoteElement(reference.rootId);
    if (root === null) {
        return true;
    }
    if (adjacentRootId(root, 'previous') !== reference.previousRootId) {
        return true;
    }
    return adjacentRootId(root, 'next') !== reference.nextRootId;
}

// --- Holding --------------------------------------------------------------

function validateReference(reference) {
    if (reference === null || typeof reference !== 'object' || typeof reference.noteId !== 'string'
        || typeof reference.keepVisible !== 'boolean') {
        throw new Error('A viewport hold needs { kind, noteId, keepVisible, ... }');
    }
    if (reference.kind === 'top') {
        if (typeof reference.top !== 'number') {
            throw new Error('A top hold needs a numeric top');
        }
        return;
    }
    if (reference.kind === 'sorted') {
        if (typeof reference.rootId !== 'string') {
            throw new Error('A sorted hold needs the edited root id');
        }
        for (const field of ['previousRootId', 'nextRootId']) {
            if (reference[field] !== null && typeof reference[field] !== 'string') {
                throw new Error(`A sorted hold needs ${field} as a string or null`);
            }
        }
        validateReference(reference.primary);
        validateReference(reference.neighbour);
        if (reference.primary.kind === 'sorted' || reference.neighbour.kind !== 'top') {
            throw new Error('A sorted hold needs a primary anchor and a neighbour top');
        }
        return;
    }
    if (reference.kind === 'text') {
        for (const field of ['screenY', 'textOffset', 'textLength', 'noteTop']) {
            if (typeof reference[field] !== 'number') {
                throw new Error(`A text hold needs a numeric ${field}`);
            }
        }
        if (typeof reference.before !== 'string' || typeof reference.after !== 'string') {
            throw new Error('A text hold needs its surrounding text');
        }
        return;
    }
    throw new Error(`Unknown viewport hold kind: ${reference.kind}`);
}

// The scroll delta that puts the reference back in place, whether it was found
// only approximately, whether a position cue may follow (only holds that keep
// the user's place through an edit; band shifts while scrolling never do), and
// the element to cue; null when its note is gone.
function locateReference(reference) {
    if (reference.kind === 'sorted') {
        if (sortedRootMoved(reference)) {
            return locateReference(reference.neighbour);
        }
        return locateReference(reference.primary);
    }
    const element = findNoteElement(reference.noteId);
    if (!element) {
        return null;
    }
    // Only a real text match places the view: a proportional guess (the text
    // did not survive rendering, e.g. Mermaid source or Markdown syntax) can
    // land anywhere in a formatted note, so the note's top is held instead.
    if (reference.kind === 'text' && !isShownCollapsed(element)) {
        const content = noteContent(element);
        const found = findTextPosition(content.textContent, reference);
        if (found.exact) {
            const y = textPositionToY(content, found.position);
            if (y !== null) {
                return {
                    delta: y - reference.screenY, approximate: false, eligible: true,
                    cueElement: blockAtTextPosition(content, found.position),
                };
            }
        }
    }
    // A collapsed note's text is hidden, and unmatched text has no place:
    // hold the note's top, keeping it in view.
    const rect = element.getBoundingClientRect();
    let target = reference.kind === 'top' ? reference.top : reference.noteTop;
    if (reference.keepVisible) {
        const inset = getViewportTopInset();
        if (target + rect.height < inset + MIN_VISIBLE_PX) {
            target = inset;
        }
    }
    let eligible = reference.keepVisible;
    if (reference.kind === 'text') {
        eligible = true;
    }
    // A note that collapsed again changed shape: the user's exact place is
    // hidden, so it always counts as approximate (and is cued).
    const approximate = isShownCollapsed(element);
    return { delta: rect.top - target, approximate, eligible, cueElement: element };
}

// The block-level element (paragraph, list item, heading…) holding a text position.
function blockAtTextPosition(content, position) {
    const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    let consumed = 0;
    let node = walker.nextNode();
    while (node !== null) {
        if (consumed + node.data.length >= position) {
            let element = node.parentElement;
            while (element !== content && getComputedStyle(element).display.startsWith('inline')) {
                element = element.parentElement;
            }
            return element;
        }
        consumed += node.data.length;
        node = walker.nextNode();
    }
    return content;
}

export function shouldShowPositionCue({ eligible, approximate, movedPx }) {
    if (typeof eligible !== 'boolean' || typeof approximate !== 'boolean' || typeof movedPx !== 'number') {
        throw new Error('shouldShowPositionCue requires eligible, approximate and movedPx');
    }
    return eligible && (approximate || Math.abs(movedPx) > CUE_MIN_MOVE_PX);
}

// A highlight over where the user's place landed: shown at full strength in
// the same frame the note lands (so it never "appears" on its own), then
// fading. An overlay anchored to the page, so it scrolls with the text and the
// note itself never changes; skipped under reduced motion or when the
// "position cue" preference is off. Returns the overlay, or null.
function showPositionCue(element) {
    if (!document.body.classList.contains('pref-position-cue')) {
        return null;
    }
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        return null;
    }
    const rect = element.getBoundingClientRect();
    if (rect.height <= 0 || rect.bottom < 0 || rect.top > window.innerHeight) {
        return null;
    }
    const overlay = document.createElement('div');
    overlay.className = 'note-position-cue';
    overlay.setAttribute('aria-hidden', 'true');
    const cue = { overlay, target: element };
    placePositionCue(cue);
    document.body.appendChild(overlay);
    // Follow the target every frame while shown: a note that collapses again
    // shrinks over several frames, and the hold may end before the fade does.
    const follow = () => {
        if (!overlay.isConnected) {
            return;
        }
        if (!cue.target.isConnected) {
            overlay.remove();
            return;
        }
        placePositionCue(cue);
        window.requestAnimationFrame(follow);
    };
    window.requestAnimationFrame(follow);
    window.setTimeout(() => overlay.remove(), CUE_DURATION_MS);
    return cue;
}

function placePositionCue(cue) {
    const rect = cue.target.getBoundingClientRect();
    cue.overlay.style.left = `${rect.left + window.scrollX - 6}px`;
    cue.overlay.style.top = `${rect.top + window.scrollY - 3}px`;
    cue.overlay.style.width = `${rect.width + 12}px`;
    cue.overlay.style.height = `${Math.min(rect.height, window.innerHeight) + 6}px`;
}

function endHold() {
    if (moduleState.session === null) {
        return;
    }
    const { end } = moduleState.session;
    moduleState.session = null;
    end();
}

export function holdViewportRoot(reference) {
    if (reference === null) {
        return;
    }
    validateReference(reference);
    endHold();

    const root = document.documentElement;
    const previousOverflowAnchor = root.style.overflowAnchor;
    root.style.overflowAnchor = 'none';
    let expectedScrollY = window.scrollY;
    const startScrollY = window.scrollY;
    let quietTimer = null;
    let cueShown = false;
    let cue = null;
    if (moduleState.lastCue !== null && moduleState.lastCue.reference === reference) {
        cueShown = true;
        cue = moduleState.lastCue.cue;
    }

    // Runs before paint (ResizeObserver), so a cue starts in the frame the
    // corrected view is first shown.
    const correct = () => {
        const located = locateReference(reference);
        if (located === null) {
            endHold();
            return;
        }
        if (Math.abs(located.delta) >= 1) {
            window.scrollBy(0, located.delta);
        }
        expectedScrollY = window.scrollY;
        // Follow the landing element as it settles (collapsing, or replaced
        // by a re-render), so the cue never covers the notes around it.
        if (cue !== null) {
            cue.target = located.cueElement;
            placePositionCue(cue);
        }
        if (!cueShown && shouldShowPositionCue({
            eligible: located.eligible, approximate: located.approximate, movedPx: window.scrollY - startScrollY,
        })) {
            cueShown = true;
            cue = showPositionCue(located.cueElement);
            moduleState.lastCue = { reference, cue };
        }
    };
    const scheduleQuietEnd = () => {
        window.clearTimeout(quietTimer);
        quietTimer = window.setTimeout(endHold, QUIET_MS);
    };
    const observer = new ResizeObserver(() => {
        correct();
        scheduleQuietEnd();
    });
    const onUserInput = () => endHold();
    // A scroll we did not cause (scrollbar drag, keyboard) is the user's.
    const onScroll = () => {
        if (Math.abs(window.scrollY - expectedScrollY) >= 1) {
            endHold();
        }
    };
    const maxTimer = window.setTimeout(endHold, MAX_HOLD_MS);

    for (const type of USER_INPUT_EVENTS) {
        window.addEventListener(type, onUserInput, { capture: true, passive: true });
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    observer.observe(notesContainer());

    moduleState.session = {
        end: () => {
            observer.disconnect();
            for (const type of USER_INPUT_EVENTS) {
                window.removeEventListener(type, onUserInput, { capture: true });
            }
            window.removeEventListener('scroll', onScroll);
            window.clearTimeout(quietTimer);
            window.clearTimeout(maxTimer);
            root.style.overflowAnchor = previousOverflowAnchor;
        },
    };
    correct();
    scheduleQuietEnd();
}
