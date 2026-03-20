import { ModeContextInstance as ModeContext } from '../mode-context.js';
import { computeScrollAnchor } from './scroll-anchor-service.js';

function getNoteElementById(noteId) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        return null;
    }
    return document.querySelector(`.note[data-note-id="${noteId}"]`);
}

function getViewportTopInset() {
    const controls = document.querySelector('.controls');
    if (!controls) {
        return 0;
    }
    const rect = controls.getBoundingClientRect();
    if (rect.height <= 0 || rect.width <= 0 || rect.bottom <= 0) {
        return 0;
    }
    return Math.max(0, Math.round(rect.bottom + 8));
}

function getViewportReferenceY(anchorBias) {
    const topInset = getViewportTopInset();
    if (anchorBias === 'center') {
        return topInset + (window.innerHeight - topInset) / 2;
    }
    if (anchorBias === 'top') {
        return topInset;
    }
    throw new Error(`Unsupported anchorBias: ${anchorBias}`);
}

function distanceToLine(rect, lineY) {
    if (lineY >= rect.top && lineY <= rect.bottom) {
        return 0;
    }
    return Math.min(Math.abs(rect.top - lineY), Math.abs(rect.bottom - lineY));
}

function findBestViewportAnchorNote() {
    const noteElements = Array.from(document.querySelectorAll('.note[data-note-id]'));
    if (noteElements.length === 0) {
        return null;
    }

    const centerRef = getViewportReferenceY('center');
    let bestElement = null;
    let bestDistance = Infinity;
    let bestCenterDistance = Infinity;
    for (const noteElement of noteElements) {
        const rect = noteElement.getBoundingClientRect();
        if (rect.height <= 0) {
            continue;
        }
        const dist = distanceToLine(rect, centerRef);
        const centerDistance = Math.abs((rect.top + rect.bottom) / 2 - centerRef);
        if (dist < bestDistance || (dist === bestDistance && centerDistance < bestCenterDistance)) {
            bestElement = noteElement;
            bestDistance = dist;
            bestCenterDistance = centerDistance;
        }
    }
    return bestElement;
}

function getScrollMaxY() {
    const doc = document.documentElement;
    return Math.max(0, Math.round(doc.scrollHeight - window.innerHeight));
}

function clampScrollY(scrollY) {
    if (typeof scrollY !== 'number' || Number.isNaN(scrollY)) {
        throw new Error('scrollY must be a number');
    }
    if (scrollY < 0) {
        return 0;
    }
    const max = getScrollMaxY();
    if (scrollY > max) {
        return max;
    }
    return Math.round(scrollY);
}

function captureScrollReference(noteId) {
    const preferredIds = [];
    if (typeof ModeContext.currentNoteId === 'string' && ModeContext.currentNoteId.length > 0) {
        preferredIds.push(ModeContext.currentNoteId);
    }
    if (typeof noteId === 'string' && noteId.length > 0 && !preferredIds.includes(noteId)) {
        preferredIds.push(noteId);
    }

    for (const candidateId of preferredIds) {
        const element = getNoteElementById(candidateId);
        if (!element) {
            continue;
        }
        return {
            noteId: candidateId,
            top: element.getBoundingClientRect().top,
        };
    }

    const anchorElement = findBestViewportAnchorNote();
    if (!anchorElement) {
        return null;
    }
    const anchorId = typeof anchorElement.dataset.noteId === 'string' ? anchorElement.dataset.noteId : '';
    if (!anchorId) {
        return null;
    }
    return {
        noteId: anchorId,
        top: anchorElement.getBoundingClientRect().top,
    };
}

function restoreScrollReference(reference) {
    if (!reference || typeof reference !== 'object') {
        return;
    }
    const targetElement = getNoteElementById(reference.noteId);
    if (!targetElement) {
        return;
    }
    const nextTop = targetElement.getBoundingClientRect().top;
    const delta = nextTop - reference.top;
    if (Math.abs(delta) < 1) {
        return;
    }
    const targetScrollY = clampScrollY(window.scrollY + delta);
    window.scrollTo(0, targetScrollY);
}

function syncLocalScrollState() {
    const tabId = ModeContext.activeTabId;
    const scrollY = Math.max(0, Math.round(window.scrollY));
    ModeContext.updateTabScroll(tabId, scrollY, false);
    ModeContext.updateTabScrollAnchor(tabId, computeScrollAnchor({ anchorBias: 'auto' }), false);
}

export function syncSearchRedactionState(noteElement) {
    if (!(noteElement instanceof HTMLElement)) {
        throw new Error('syncSearchRedactionState requires note element');
    }
    const noteId = typeof noteElement.dataset.noteId === 'string' ? noteElement.dataset.noteId : '';
    const isSearchRedacted = noteElement.dataset.searchRedacted === 'true';
    if (!isSearchRedacted) {
        noteElement.classList.remove('search-redacted');
        noteElement.classList.remove('search-revealed');
        if (noteId) {
            ModeContext.hideActiveTabRedactedNote(noteId);
        }
        return false;
    }

    if (!noteId) {
        throw new Error('Redacted note missing data-note-id');
    }

    const isRevealed = ModeContext.isActiveTabRedactedNoteRevealed(noteId);
    noteElement.classList.toggle('search-redacted', !isRevealed);
    noteElement.classList.toggle('search-revealed', isRevealed);
    return isRevealed;
}

export function setNoteSearchRedactionState(noteElement, isSearchRedacted) {
    if (!(noteElement instanceof HTMLElement)) {
        throw new Error('setNoteSearchRedactionState requires note element');
    }
    if (typeof isSearchRedacted !== 'boolean') {
        throw new Error('isSearchRedacted must be a boolean');
    }
    noteElement.dataset.searchRedacted = isSearchRedacted ? 'true' : 'false';
    return syncSearchRedactionState(noteElement);
}

export function revealRedactedNoteWithScrollPreservation(noteId) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('revealRedactedNoteWithScrollPreservation requires noteId');
    }
    const noteElement = getNoteElementById(noteId);
    if (!noteElement) {
        return { revealed: false, reason: 'missing' };
    }
    if (noteElement.dataset.searchRedacted !== 'true') {
        return { revealed: false, reason: 'not_redacted' };
    }
    if (ModeContext.isActiveTabRedactedNoteRevealed(noteId)) {
        return { revealed: false, reason: 'already_revealed' };
    }

    const reference = captureScrollReference(noteId);
    ModeContext.revealActiveTabRedactedNote(noteId);
    syncSearchRedactionState(noteElement);
    restoreScrollReference(reference);

    window.requestAnimationFrame(() => {
        restoreScrollReference(reference);
        syncLocalScrollState();
    });

    return { revealed: true, reason: 'revealed' };
}
