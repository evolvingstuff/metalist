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
// Shorter text fragments match too easily to count as the same place.
const MIN_MATCH_CHARS = 8;

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
// The text node and offset of character position `position` in content's
// text. Line breaks add no text, so the end of one line and the start of the
// next are the same position: `affinity` 'forward' picks the next line's
// start (a click on a line, a source line), 'backward' the previous line's
// end (a caret left after typing at a line's end).
function textPositionToNodePoint(content, position, affinity) {
    if (affinity !== 'forward' && affinity !== 'backward') {
        throw new Error(`Unknown text affinity: ${affinity}`);
    }
    const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    let consumed = 0;
    let last = null;
    let node = walker.nextNode();
    while (node !== null) {
        const end = consumed + node.data.length;
        if (position < end || (affinity === 'backward' && position === end)) {
            return { node, offset: position - consumed };
        }
        consumed = end;
        last = node;
        node = walker.nextNode();
    }
    if (last !== null && position === consumed) {
        return { node: last, offset: last.data.length };
    }
    return null;
}

// Screen Y of character position `position` in content's text, or null.
function textPositionToY(content, position, affinity) {
    const point = textPositionToNodePoint(content, position, affinity);
    if (point === null) {
        return null;
    }
    const range = document.createRange();
    range.setStart(point.node, point.offset);
    range.collapse(true);
    const rects = range.getClientRects();
    if (rects.length > 0) {
        return rects[0].top;
    }
    const parentRect = point.node.parentElement.getBoundingClientRect();
    return parentRect.height > 0 ? parentRect.top : null;
}

// Only leaving edit mode may show a position cue (captureNoteAnchor records
// the note's first line for exactly that); entering edit mode, switching
// notes and band shifts never do.
function isEditExitAnchor(reference) {
    return Object.prototype.hasOwnProperty.call(reference, 'contentTop');
}

// Screen Y of the content's first line of text (its box top when it has no text).
function firstLineTop(content) {
    const y = textPositionToY(content, 0, 'forward');
    if (y === null) {
        return content.getBoundingClientRect().top;
    }
    return y;
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
    const trimmedAfter = anchor.after.trimStart();
    for (const [needle, shift] of [
        [anchor.before + anchor.after, anchor.before.length],
        // Rendering can drop whitespace the user just typed next to the caret.
        [trimmedBefore + trimmedAfter, trimmedBefore.length],
    ]) {
        if (needle.length >= MIN_MATCH_CHARS) {
            const position = nearest(needle, shift);
            if (position !== null) {
                return { position, exact: true, affinity: anchor.affinity };
            }
        }
    }
    // Source and rendering differ in markup next to the place (list markers,
    // heading hashes, emphasis): match the longest run of the text right after
    // it, then right before it, that survives.
    for (let length = trimmedAfter.length; length >= MIN_MATCH_CHARS; length -= 1) {
        const position = nearest(trimmedAfter.slice(0, length), 0);
        if (position !== null) {
            return { position, exact: true, affinity: 'forward' };
        }
    }
    for (let length = trimmedBefore.length; length >= MIN_MATCH_CHARS; length -= 1) {
        const position = nearest(trimmedBefore.slice(trimmedBefore.length - length), length);
        if (position !== null) {
            return { position, exact: true, affinity: 'backward' };
        }
    }
    const proportional = Math.round(anchor.textOffset * text.length / Math.max(1, anchor.textLength));
    return { position: Math.min(text.length, Math.max(0, proportional)), exact: false, affinity: anchor.affinity };
}

// A DOM point at the very start of a text node belongs to that line; any
// other point (e.g. the end of a line just typed) to the text before it.
function affinityOfDomPoint(node, offset) {
    if (node.nodeType === Node.TEXT_NODE && offset === 0) {
        return 'forward';
    }
    return 'backward';
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
    // Where the note's first line of text is: a note that collapses again
    // keeps its (first-line) row there.
    const contentTop = firstLineTop(content);
    const inset = getViewportTopInset();
    const viewportBottom = window.innerHeight;
    const textAnchorAt = (node, offset) => {
        const text = content.textContent;
        const textOffset = textOffsetOf(content, node, offset);
        const affinity = affinityOfDomPoint(node, offset);
        const screenY = textPositionToY(content, textOffset, affinity);
        if (screenY === null) {
            return null;
        }
        return {
            kind: 'text', noteId, screenY, textOffset, textLength: text.length,
            before: text.slice(Math.max(0, textOffset - CONTEXT_CHARS), textOffset),
            after: text.slice(textOffset, textOffset + CONTEXT_CHARS),
            noteTop, contentTop, keepVisible: true, affinity,
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

    return { kind: 'top', noteId, top: noteTop, contentTop, keepVisible: true };
}

// What to keep in place when a click enters edit mode: the clicked text (it
// stays under the pointer once the note shows its editable source), or the
// note's top when the click was not on text (e.g. a rendered diagram).
export function captureClickAnchor(noteElement, x, y) {
    if (typeof x !== 'number' || typeof y !== 'number') {
        throw new Error('captureClickAnchor requires click coordinates');
    }
    const noteId = noteElement.dataset.noteId;
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('captureClickAnchor requires a note element with an id');
    }
    const noteTop = noteElement.getBoundingClientRect().top;
    const content = noteContent(noteElement);
    const diagramAnchor = captureDiagramClickAnchor({ content, noteId, noteTop, x, y });
    if (diagramAnchor !== null) {
        return diagramAnchor;
    }
    const position = caretPositionAt(x, y);
    if (position !== null && position.node.nodeType === Node.TEXT_NODE && content.contains(position.node)) {
        const text = content.textContent;
        const textOffset = textOffsetOf(content, position.node, position.offset);
        const affinity = affinityOfDomPoint(position.node, position.offset);
        const screenY = textPositionToY(content, textOffset, affinity);
        if (screenY !== null) {
            return {
                kind: 'text', noteId, screenY, textOffset, textLength: text.length,
                before: text.slice(Math.max(0, textOffset - CONTEXT_CHARS), textOffset),
                after: text.slice(textOffset, textOffset + CONTEXT_CHARS),
                noteTop, keepVisible: false, clickX: x, clickY: y, affinity,
            };
        }
    }
    return { kind: 'top', noteId, top: noteTop, keepVisible: false, clickX: x, clickY: y };
}

const MERMAID_BLOCK_SELECTOR = '.meta-mermaid-diagram, pre.meta-mermaid-source';

// How a Mermaid node's label can appear in its source: A[label], C{label},
// D(label), quoted labels, and the other bracket shapes.
function mermaidLabelNeedles(label) {
    const needles = [];
    for (const [open, close] of [
        ['[', ']'], ['{', '}'], ['(', ')'], ['["', '"]'], ['{"', '"}'], ['("', '")'],
        ['[[', ']]'], ['((', '))'], ['([', '])'], ['{{', '}}'], ['>', ']'],
    ]) {
        needles.push({ text: `${open}${label}${close}`, shift: open.length });
    }
    return needles;
}

// A click on a rendered Mermaid diagram: the browser's text hit-testing is
// unreliable inside it and its text is in drawing order, so the diagram's own
// structure says what was clicked. A box maps to its label in the source (that
// source line goes under the pointer); anywhere else maps to the diagram's
// ```mermaid line, held where the diagram's top was. Null when the click was
// not on a diagram.
function captureDiagramClickAnchor({ content, noteId, noteTop, x, y }) {
    const hit = document.elementFromPoint(x, y);
    if (hit === null) {
        return null;
    }
    const block = hit.closest(MERMAID_BLOCK_SELECTOR);
    if (block === null || !content.contains(block)) {
        return null;
    }
    const base = { kind: 'source', noteId, noteTop, keepVisible: false, clickX: x, clickY: y };
    const node = hit.closest('g.node');
    if (node !== null) {
        const labelElement = node.querySelector('.nodeLabel');
        if (labelElement !== null && labelElement.textContent.trim().length > 0) {
            return {
                ...base, needles: mermaidLabelNeedles(labelElement.textContent.trim()), occurrence: 0,
                screenY: labelElement.getBoundingClientRect().top,
            };
        }
    }
    const blocks = [...content.querySelectorAll(MERMAID_BLOCK_SELECTOR)];
    return {
        ...base, needles: [{ text: '```mermaid', shift: 0 }], occurrence: blocks.indexOf(block),
        screenY: block.getBoundingClientRect().top,
    };
}

// The text position a source anchor names: the `occurrence`-th match, in text
// order, of any of its needles; null when absent (e.g. still the rendered view).
function findSourcePosition(text, reference) {
    const positions = [];
    for (const needle of reference.needles) {
        let index = text.indexOf(needle.text);
        while (index !== -1) {
            positions.push(index + needle.shift);
            index = text.indexOf(needle.text, index + 1);
        }
    }
    positions.sort((first, second) => first - second);
    if (reference.occurrence >= positions.length) {
        return null;
    }
    return positions[reference.occurrence];
}


// Puts the caret of the now-editable note where the user clicked, never
// scrolling: at the clicked text when it is found exactly, otherwise at
// whatever is under the pointer now that the view is held (e.g. the source of
// a clicked diagram), otherwise at the start of the note.
export function placeCaretAtClickAnchor(noteElement, reference) {
    validateReference(reference);
    if (typeof reference.clickX !== 'number' || typeof reference.clickY !== 'number') {
        throw new Error('placeCaretAtClickAnchor requires a click anchor');
    }
    const content = noteContent(noteElement);
    let point = null;
    if (reference.kind === 'text') {
        const found = findTextPosition(content.textContent, reference);
        if (found.exact) {
            point = textPositionToNodePoint(content, found.position, found.affinity);
        }
    }
    if (reference.kind === 'source') {
        const position = findSourcePosition(content.textContent, reference);
        if (position !== null) {
            point = textPositionToNodePoint(content, position, 'forward');
        }
    }
    if (point === null) {
        const underPointer = caretPositionAt(reference.clickX, reference.clickY);
        if (underPointer !== null && content.contains(underPointer.node)) {
            point = underPointer;
        }
    }
    if (point === null) {
        point = { node: content, offset: 0 };
    }
    const range = document.createRange();
    range.setStart(point.node, point.offset);
    range.collapse(true);
    content.focus({ preventScroll: true });
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
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
    if (reference.kind === 'source') {
        if (!Array.isArray(reference.needles) || reference.needles.length === 0
            || !reference.needles.every((needle) => typeof needle.text === 'string' && needle.text.length > 0
                && Number.isInteger(needle.shift))) {
            throw new Error('A source hold needs needles');
        }
        if (!Number.isInteger(reference.occurrence) || reference.occurrence < 0) {
            throw new Error('A source hold needs an occurrence index');
        }
        for (const field of ['screenY', 'noteTop']) {
            if (typeof reference[field] !== 'number') {
                throw new Error(`A source hold needs a numeric ${field}`);
            }
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
        if (reference.affinity !== 'forward' && reference.affinity !== 'backward') {
            throw new Error('A text hold needs its affinity');
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
    if (reference.kind === 'source' && !isShownCollapsed(element)) {
        const content = noteContent(element);
        const position = findSourcePosition(content.textContent, reference);
        if (position !== null) {
            const y = textPositionToY(content, position, 'forward');
            if (y !== null) {
                return { delta: y - reference.screenY, displacedPx: 0, approximate: false, eligible: false, cueElement: element };
            }
        }
    }
    // Only a real text match places the view: a proportional guess (the text
    // did not survive rendering, e.g. Mermaid source or Markdown syntax) can
    // land anywhere in a formatted note, so the note's top is held instead.
    if (reference.kind === 'text') {
        const content = noteContent(element);
        const found = findTextPosition(content.textContent, reference);
        if (found.exact) {
            const y = textPositionToY(content, found.position, found.affinity);
            if (y !== null && !isShownCollapsed(element)) {
                return {
                    delta: y - reference.screenY, displacedPx: 0, approximate: false,
                    eligible: isEditExitAnchor(reference), cueElement: blockAtTextPosition(content, found.position),
                };
            }
        }
    }
    const rect = element.getBoundingClientRect();
    // A note that collapsed again: its first line of text stays where the
    // note's first line was while editing, keeping the row in view.
    if (isShownCollapsed(element) && Object.prototype.hasOwnProperty.call(reference, 'contentTop')) {
        if (typeof reference.contentTop !== 'number') {
            throw new Error('A hold contentTop must be a number');
        }
        const heldDelta = firstLineTop(noteContent(element)) - reference.contentTop;
        let delta = heldDelta;
        if (reference.keepVisible) {
            const inset = getViewportTopInset();
            if (rect.top - delta + rect.height < inset + MIN_VISIBLE_PX) {
                delta = rect.top - inset;
            }
        }
        return {
            delta, displacedPx: Math.abs(delta - heldDelta), approximate: true,
            eligible: isEditExitAnchor(reference), cueElement: element,
        };
    }
    // Unmatched text has no place, and a hold without a first line to keep
    // holds the note's top, keeping it in view.
    const heldTarget = reference.kind === 'top' ? reference.top : reference.noteTop;
    let target = heldTarget;
    if (reference.keepVisible) {
        const inset = getViewportTopInset();
        if (target + rect.height < inset + MIN_VISIBLE_PX) {
            target = inset;
        }
    }
    const eligible = isEditExitAnchor(reference);
    // A note that collapsed again changed shape: the user's exact place is
    // hidden, so it always counts as approximate (and is cued).
    const approximate = isShownCollapsed(element);
    return { delta: rect.top - target, displacedPx: Math.abs(target - heldTarget), approximate, eligible, cueElement: element };
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

// `displacedPx`: how far the user's place ends up from where it was on
// screen (scrolling that keeps it still does not count). The cue marks only
// a place that collapsed or could not be kept where it was.
export function shouldShowPositionCue({ eligible, approximate, displacedPx }) {
    if (typeof eligible !== 'boolean' || typeof approximate !== 'boolean' || typeof displacedPx !== 'number') {
        throw new Error('shouldShowPositionCue requires eligible, approximate and displacedPx');
    }
    return eligible && (approximate || displacedPx > CUE_MIN_MOVE_PX);
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
        const scrolledFrom = window.scrollY;
        if (Math.abs(located.delta) >= 1) {
            window.scrollBy(0, located.delta);
        }
        // What the page could not scroll (its top or bottom) leaves the place displaced.
        const unscrolled = Math.abs(located.delta - (window.scrollY - scrolledFrom));
        expectedScrollY = window.scrollY;
        // Follow the landing element as it settles (collapsing, or replaced
        // by a re-render), so the cue never covers the notes around it.
        if (cue !== null) {
            cue.target = located.cueElement;
            placePositionCue(cue);
        }
        if (!cueShown && shouldShowPositionCue({
            eligible: located.eligible, approximate: located.approximate, displacedPx: located.displacedPx + unscrolled,
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
