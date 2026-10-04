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

const moduleState = ApplicationState.createFields('viewport-hold-service', {
    session: null,
});

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

// Scroll delta that puts the reference back in place, or null when its note is gone.
function correctionDelta(reference) {
    const element = findNoteElement(reference.noteId);
    if (!element) {
        return null;
    }
    if (reference.kind === 'text' && !element.classList.contains('collapsed')) {
        const content = noteContent(element);
        const found = findTextPosition(content.textContent, reference);
        const y = textPositionToY(content, found.position);
        if (y !== null) {
            return y - reference.screenY;
        }
    }
    // A collapsed note's text is hidden: hold its top, keeping it in view.
    const rect = element.getBoundingClientRect();
    let target = reference.kind === 'top' ? reference.top : reference.noteTop;
    if (reference.keepVisible) {
        const inset = getViewportTopInset();
        if (target + rect.height < inset + MIN_VISIBLE_PX) {
            target = inset;
        }
    }
    return rect.top - target;
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
    let quietTimer = null;

    const correct = () => {
        const delta = correctionDelta(reference);
        if (delta === null) {
            endHold();
            return;
        }
        if (Math.abs(delta) >= 1) {
            window.scrollBy(0, delta);
        }
        expectedScrollY = window.scrollY;
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
