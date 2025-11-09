let activeEditableElement = null;
let activeNoteId = null;
let savedRange = null;
let trackingInitialized = false;

function isNodeInsideActiveEditable(node) {
    if (!node || !activeEditableElement) {
        return false;
    }
    return activeEditableElement.contains(node);
}

function handleSelectionChange() {
    if (!activeEditableElement) {
        savedRange = null;
        return;
    }

    const selection = document.getSelection();
    if (!selection || selection.rangeCount === 0) {
        savedRange = null;
        return;
    }

    const range = selection.getRangeAt(0);
    if (isNodeInsideActiveEditable(range.startContainer)) {
        savedRange = range.cloneRange();
    }
}

function createCollapsedRangeAtEnd() {
    if (!activeEditableElement) {
        return null;
    }
    const range = document.createRange();
    range.selectNodeContents(activeEditableElement);
    range.collapse(false);
    return range;
}

export function initSelectionTracking() {
    if (trackingInitialized) {
        return;
    }
    document.addEventListener('selectionchange', handleSelectionChange, true);
    trackingInitialized = true;
}

export function setActiveEditable(noteId, element) {
    if (element && !(element instanceof HTMLElement)) {
        throw new Error('Active editable element must be an HTMLElement');
    }
    activeEditableElement = element || null;
    activeNoteId = element ? noteId : null;
    savedRange = null;
}

export function clearActiveEditable() {
    activeEditableElement = null;
    activeNoteId = null;
    savedRange = null;
}

export function getActiveEditable() {
    return activeEditableElement;
}

export function getActiveNoteId() {
    return activeNoteId;
}

export function restoreSelection() {
    if (!activeEditableElement) {
        return false;
    }
    const selection = document.getSelection();
    if (!selection) {
        return false;
    }
    selection.removeAllRanges();
    const rangeToRestore = savedRange ? savedRange.cloneRange() : createCollapsedRangeAtEnd();
    if (!rangeToRestore) {
        return false;
    }
    selection.addRange(rangeToRestore);
    return Boolean(savedRange);
}

export function captureSelectionSnapshot() {
    handleSelectionChange();
}

export function getSavedRangeClone() {
    return savedRange ? savedRange.cloneRange() : null;
}

export function selectionInsideActiveEditable() {
    if (!activeEditableElement) {
        return false;
    }
    const selection = document.getSelection();
    if (!selection || selection.rangeCount === 0) {
        return false;
    }
    const range = selection.getRangeAt(0);
    return isNodeInsideActiveEditable(range.startContainer);
}
