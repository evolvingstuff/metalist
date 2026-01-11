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
    const controls = document.querySelector('.controls');
    if (!controls) {
        return 0;
    }
    const rect = controls.getBoundingClientRect();
    if (rect.height <= 0 || rect.width <= 0) {
        return 0;
    }
    if (rect.bottom <= 0) {
        return 0;
    }
    const bufferPx = 8;
    return Math.max(0, Math.round(rect.bottom + bufferPx));
}

function getScrollMaxY() {
    const doc = document.documentElement;
    const max = doc.scrollHeight - window.innerHeight;
    return Math.max(0, Math.round(max));
}

function escapeNoteId(noteId) {
    if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
        return CSS.escape(noteId);
    }
    return noteId.replace(/"/g, '\\"');
}

function getNoteElementById(noteId) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        return null;
    }
    const escaped = escapeNoteId(noteId);
    return document.querySelector(`.note[data-note-id="${escaped}"]`);
}

function getNoteContentElement(noteElement) {
    return noteElement;
}

function getOrderedRootNoteIds() {
    const container = document.getElementById('notes-container');
    if (!container) {
        throw new Error('notes-container not found');
    }
	const noteElements = Array.from(container.querySelectorAll('.note[data-note-id]'));
	const rootIds = [];
	const rootParentSentinels = new Set(['', 'null', 'undefined', 'none']);
	for (const element of noteElements) {
		const rawParent = element?.getAttribute('data-parent-id');
		const normalized = (typeof rawParent === 'string' ? rawParent : '').trim().toLowerCase();
		const isRoot = rootParentSentinels.has(normalized);
		if (!isRoot) continue;
		const noteId = (element?.dataset?.noteId || '').toString();
		if (!noteId) continue;
		rootIds.push(noteId);
	}
	return rootIds;
}

function pickFirstExistingId(noteIds) {
    for (const noteId of noteIds || []) {
        if (typeof noteId !== 'string' || noteId.length === 0) continue;
        if (getNoteElementById(noteId)) {
            return noteId;
        }
    }
    return null;
}

function computeScrollYForElement(contentElement, anchorBias, intraOffset) {
    const rect = contentElement.getBoundingClientRect();
    const docTop = rect.top + window.scrollY;
    const referenceY = getViewportReferenceY(anchorBias);
    const clampedOffset = Math.round(clampNumber(intraOffset, 0, Math.max(0, rect.height)));
    const target = docTop - (referenceY - clampedOffset);
    return Math.round(clampNumber(target, 0, getScrollMaxY()));
}

export function restoreScrollFromAnchor(savedAnchor, options) {
	if (options === null || typeof options !== 'object') {
		throw new Error('restoreScrollFromAnchor requires options object');
	}
	const scrollYFallback = typeof options.scrollYFallback === 'number' ? options.scrollYFallback : 0;
	const orderedRootIds = getOrderedRootNoteIds();

    if (!savedAnchor || orderedRootIds.length === 0) {
        const fallback = Math.round(clampNumber(scrollYFallback, 0, getScrollMaxY()));
        window.scrollTo(0, fallback);
        return { restored: false, reason: 'no_anchor_or_empty' };
    }

	let anchorBias = savedAnchor.anchorBias;
	if (typeof anchorBias === 'undefined') {
		anchorBias = 'center';
	}
	const intraOffset = typeof savedAnchor.intraOffset === 'number' ? savedAnchor.intraOffset : 0;

    let targetId = null;
    if (typeof savedAnchor.anchorId === 'string' && savedAnchor.anchorId.length > 0) {
        if (getNoteElementById(savedAnchor.anchorId)) {
            targetId = savedAnchor.anchorId;
        }
    }

    if (!targetId) {
        const beltCandidate = pickFirstExistingId([...(savedAnchor.beltPrev || []), ...(savedAnchor.beltNext || [])]);
        if (beltCandidate) {
            targetId = beltCandidate;
        }
    }

    if (!targetId) {
        const domIndex = savedAnchor.anchorSortKey && typeof savedAnchor.anchorSortKey.domIndex === 'number'
            ? savedAnchor.anchorSortKey.domIndex
            : null;
		if (typeof domIndex === 'number' && domIndex >= 0 && orderedRootIds.length > 0) {
			const idx = Math.round(clampNumber(domIndex, 0, orderedRootIds.length - 1));
			const candidate = orderedRootIds[idx];
			targetId = typeof candidate === 'string' && candidate.length > 0 ? candidate : null;
		}
	}

    if (!targetId) {
        window.scrollTo(0, 0);
        return { restored: false, reason: 'no_targets' };
    }

    const noteElement = getNoteElementById(targetId);
    if (!noteElement) {
        window.scrollTo(0, 0);
        return { restored: false, reason: 'target_missing' };
    }

    const contentElement = getNoteContentElement(noteElement);
    const targetScrollY = computeScrollYForElement(contentElement, anchorBias, intraOffset);
    window.scrollTo(0, targetScrollY);
    return { restored: true, reason: 'anchor' };
}

export function scrollNoteIntoView(noteId, options) {
	if (options === null || typeof options !== 'object') {
		throw new Error('scrollNoteIntoView requires options object');
	}
	if (typeof noteId !== 'string' || noteId.length === 0) {
		throw new Error('scrollNoteIntoView requires a non-empty noteId');
	}

    const noteElement = getNoteElementById(noteId);
    if (!noteElement) {
        return { scrolled: false, reason: 'missing' };
    }

    const topInset = getViewportTopInset();
    const padding = typeof options.padding === 'number' && options.padding >= 0 ? options.padding : 12;

    const rect = noteElement.getBoundingClientRect();
    const visibleTop = topInset + padding;
    const visibleBottom = window.innerHeight - padding;
    const fullyVisible = rect.top >= visibleTop && rect.bottom <= visibleBottom;
    if (fullyVisible) {
        return { scrolled: false, reason: 'already_visible' };
    }

    const docTop = rect.top + window.scrollY;
    const target = docTop - visibleTop;
    const clamped = Math.round(clampNumber(target, 0, getScrollMaxY()));
    window.scrollTo(0, clamped);
    return { scrolled: true, reason: 'scroll' };
}
