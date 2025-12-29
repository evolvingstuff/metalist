const DEFAULT_BELT_SIZE = 4;

function clampNumber(value, min, max) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        throw new Error('clampNumber requires a number');
    }
    if (value < min) return min;
    if (value > max) return max;
    return value;
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

function getViewportTopInset() {
    const candidates = [
        document.querySelector('.global-controls'),
        document.querySelector('.controls'),
        document.getElementById('search-contexts-list'),
        document.getElementById('tab-indicator'),
    ].filter(Boolean);

    let maxBottom = 0;
    for (const element of candidates) {
        const rect = element.getBoundingClientRect();
        // Ignore elements far below the fold.
        if (rect.top > 200) {
            continue;
        }
        if (rect.bottom > maxBottom) {
            maxBottom = rect.bottom;
        }
    }
    return Math.max(0, Math.round(maxBottom));
}

function requireNotesContainer() {
    const container = document.getElementById('notes-container');
    if (!container) {
        throw new Error('notes-container not found');
    }
    return container;
}

function isRootNoteElement(element) {
    const rawParent = element?.getAttribute('data-parent-id');
    const normalized = (typeof rawParent === 'string' ? rawParent : '').trim().toLowerCase();
    return normalized === '' || normalized === 'null' || normalized === 'undefined' || normalized === 'none';
}

function getNoteId(element) {
    return (element?.dataset?.noteId || '').toString();
}

function collectRootNotesInDomOrder(container) {
    const noteElements = [];
    const noteIds = [];
    const allNotes = Array.from(container.querySelectorAll('.note[data-note-id]'));
    for (const element of allNotes) {
        if (!isRootNoteElement(element)) continue;
        const noteId = getNoteId(element);
        if (!noteId) continue;
        noteElements.push(element);
        noteIds.push(noteId);
    }
    return { noteElements, noteIds };
}

function getNoteContentElement(noteElement) {
    if (!noteElement || typeof noteElement.querySelector !== 'function') {
        throw new Error('noteElement must be a DOM element');
    }
    return noteElement;
}

function distanceToLine(rect, lineY) {
    if (lineY >= rect.top && lineY <= rect.bottom) {
        return 0;
    }
    return Math.min(Math.abs(rect.top - lineY), Math.abs(rect.bottom - lineY));
}

function findAnchorIndex(noteElements, anchorBias) {
    const lineY = getViewportReferenceY(anchorBias);
    let bestIndex = -1;
    let bestDistance = Infinity;
    let bestCenterDistance = Infinity;

    for (let i = 0; i < noteElements.length; i += 1) {
        const noteElement = noteElements[i];
        if (!noteElement) continue;
        const blockElement = getNoteContentElement(noteElement);
        const rect = blockElement.getBoundingClientRect();
        if (rect.height <= 0) continue;

        const dist = distanceToLine(rect, lineY);
        const centerDist = Math.abs((rect.top + rect.bottom) / 2 - lineY);
        if (dist < bestDistance || (dist === bestDistance && centerDist < bestCenterDistance)) {
            bestIndex = i;
            bestDistance = dist;
            bestCenterDistance = centerDist;
        }
    }

    return bestIndex;
}

export function computeScrollAnchor(options = {}) {
    const requestedBias = options.anchorBias || 'center';
    const beltSize = typeof options.beltSize === 'number' ? options.beltSize : DEFAULT_BELT_SIZE;
    if (!Number.isInteger(beltSize) || beltSize < 0 || beltSize > 10) {
        throw new Error('beltSize must be an integer between 0 and 10');
    }

    const container = options.container || requireNotesContainer();
    const { noteElements, noteIds } = collectRootNotesInDomOrder(container);
    if (noteIds.length === 0) {
        return null;
    }

    let anchorBias = requestedBias;
    let anchorIndex = -1;
    if (requestedBias === 'auto') {
        const topRef = getViewportReferenceY('top');
        let bestPinnedIndex = -1;
        let bestPinnedDistance = Infinity;
        for (let i = 0; i < noteElements.length; i += 1) {
            const element = noteElements[i];
            if (!element) continue;
            const rect = element.getBoundingClientRect();
            if (rect.bottom <= topRef) continue;
            const dist = Math.abs(rect.top - topRef);
            if (dist <= 80 && dist < bestPinnedDistance) {
                bestPinnedIndex = i;
                bestPinnedDistance = dist;
            }
        }
        if (bestPinnedIndex >= 0) {
            anchorBias = 'top';
            anchorIndex = bestPinnedIndex;
        } else {
            anchorBias = 'center';
            anchorIndex = findAnchorIndex(noteElements, anchorBias);
        }
    } else {
        if (anchorBias !== 'center' && anchorBias !== 'top') {
            throw new Error(`Unsupported anchorBias: ${anchorBias}`);
        }
        anchorIndex = findAnchorIndex(noteElements, anchorBias);
    }

    if (anchorIndex < 0 || anchorIndex >= noteIds.length) {
        return null;
    }

    const anchorElement = noteElements[anchorIndex];
    const anchorId = noteIds[anchorIndex];
    if (!anchorElement || !anchorId) {
        return null;
    }

    const blockElement = getNoteContentElement(anchorElement);
    const rect = blockElement.getBoundingClientRect();
    const referenceY = getViewportReferenceY(anchorBias);
    const rawOffset = referenceY - rect.top;
    const intraOffset = Math.round(clampNumber(rawOffset, 0, Math.max(0, rect.height)));

    const prevSlice = noteIds.slice(Math.max(0, anchorIndex - beltSize), anchorIndex);
    const nextSlice = noteIds.slice(anchorIndex + 1, anchorIndex + 1 + beltSize);

    return {
        anchorId,
        anchorBias,
        intraOffset,
        beltPrev: prevSlice.reverse(),
        beltNext: nextSlice,
        anchorSortKey: { domIndex: anchorIndex },
    };
}
