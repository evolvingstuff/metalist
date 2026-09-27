// Keeps the content the user is looking at still while view diffs add or
// remove roots above the viewport (the loaded band of roots moving). Records
// the top visible root's on-screen position before a diff and scrolls by any
// shift afterwards, re-checking briefly because images, diagrams, and link
// titles can change height after insertion. Corrections stop as soon as the
// user scrolls.

const FOLLOW_UP_DELAYS_MS = [150, 400, 1000];

function rootNotes() {
    const container = document.getElementById('notes-container');
    if (!container) {
        throw new Error('notes-container not found');
    }
    return container.querySelectorAll(':scope > .note[data-note-id]');
}

function findRootElement(noteId) {
    for (const element of rootNotes()) {
        if (element.dataset.noteId === noteId) return element;
    }
    return null;
}

export function captureViewportRoot() {
    for (const element of rootNotes()) {
        const rect = element.getBoundingClientRect();
        if (rect.bottom > 0) {
            return { noteId: element.dataset.noteId, top: rect.top };
        }
    }
    return null;
}

function correctTowards(reference) {
    const element = findRootElement(reference.noteId);
    if (!element) {
        return false;
    }
    const delta = element.getBoundingClientRect().top - reference.top;
    if (Math.abs(delta) >= 1) {
        window.scrollBy(0, delta);
    }
    return true;
}

export function holdViewportRoot(reference) {
    if (reference === null) {
        return;
    }
    if (typeof reference !== 'object' || typeof reference.noteId !== 'string' || typeof reference.top !== 'number') {
        throw new Error('holdViewportRoot requires a captured viewport root');
    }
    if (!correctTowards(reference)) {
        return;
    }
    let expectedScrollY = window.scrollY;
    const followUp = () => {
        // The user scrolled since our last correction: their position wins.
        if (Math.abs(window.scrollY - expectedScrollY) >= 1) {
            return false;
        }
        if (!correctTowards(reference)) {
            return false;
        }
        expectedScrollY = window.scrollY;
        return true;
    };
    window.requestAnimationFrame(() => {
        if (!followUp()) return;
        for (const delayMs of FOLLOW_UP_DELAYS_MS) {
            window.setTimeout(followUp, delayMs);
        }
    });
}
