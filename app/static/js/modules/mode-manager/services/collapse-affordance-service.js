import { NotesAPI } from '../../api-client.js';
import { syncCollapsedStatusPreview } from './status-collapse-preview-service.js';

const NOTE_SELECTOR = '.note';
const NOTE_CONTENT_SELECTOR = '.note-content';
const COLLAPSED_DATA_KEY = 'isCollapsed';
const CAN_COLLAPSE_DATA_KEY = 'canCollapse';
const DELTA_TOLERANCE = 1;
const META_CSV_SELECTOR = '.meta-csv';
const PENDING_COLLAPSE_IMAGE_ELEMENTS = new WeakSet();

function parsePixels(value) {
    if (!value) {
        return 0;
    }
    const numeric = parseFloat(value);
    return Number.isFinite(numeric) ? numeric : 0;
}

function hasChildren(noteElement) {
    if (noteElement.dataset.hasChildren === 'true') {
        return true;
    }
    const childrenContainer = noteElement.querySelector(':scope > .note-children');
    if (!childrenContainer) {
        return false;
    }
    return childrenContainer.children.length > 0;
}

function contentHasAdditionalLines(contentElement) {
    const style = window.getComputedStyle(contentElement);
    const lineHeight = parsePixels(style.lineHeight);
    if (lineHeight <= 0) {
        return contentElement.scrollHeight - contentElement.clientHeight > DELTA_TOLERANCE;
    }

    const paddingTop = parsePixels(style.paddingTop);
    const paddingBottom = parsePixels(style.paddingBottom);
    const effectiveContentHeight = contentElement.scrollHeight - paddingTop - paddingBottom;
    return effectiveContentHeight - lineHeight > DELTA_TOLERANCE;
}

function refreshAffordanceAfterPendingImagesLoad(noteElement, contentElement) {
    if (!noteElement || !contentElement) {
        throw new Error('refreshAffordanceAfterPendingImagesLoad requires note and content elements');
    }
    const imageElements = contentElement.querySelectorAll('img');
    for (const imageElement of imageElements) {
        if (!(imageElement instanceof HTMLImageElement)) {
            continue;
        }
        if (imageElement.complete) {
            continue;
        }
        if (PENDING_COLLAPSE_IMAGE_ELEMENTS.has(imageElement)) {
            continue;
        }

        const handleImageSettled = () => {
            imageElement.removeEventListener('load', handleImageSettled);
            imageElement.removeEventListener('error', handleImageSettled);
            PENDING_COLLAPSE_IMAGE_ELEMENTS.delete(imageElement);
            if (!noteElement.isConnected) {
                return;
            }
            queueMicrotask(() => {
                if (!noteElement.isConnected) {
                    return;
                }
                updateCollapseAffordanceForNote(noteElement);
            });
        };

        PENDING_COLLAPSE_IMAGE_ELEMENTS.add(imageElement);
        imageElement.addEventListener('load', handleImageSettled, { once: true });
        imageElement.addEventListener('error', handleImageSettled, { once: true });
    }
}

export function updateCollapseAffordances(root) {
    if (!root) {
        throw new Error('updateCollapseAffordances requires root node');
    }
    const noteElements = root.querySelectorAll(NOTE_SELECTOR);
    noteElements.forEach((note) => {
        updateCollapseAffordanceForNote(note);
    });
}

export function updateCollapseAffordancesForNotes(noteElements) {
    if (!noteElements) {
        throw new Error('updateCollapseAffordancesForNotes requires note elements');
    }
    for (const noteElement of noteElements) {
        updateCollapseAffordanceForNote(noteElement);
    }
}

export function updateCollapseAffordanceForNote(noteElement) {
    if (!noteElement) {
        throw new Error('updateCollapseAffordanceForNote called without a note element');
    }
    if (!noteElement.classList || !noteElement.classList.contains('note')) {
        throw new Error('updateCollapseAffordanceForNote requires an element with class note');
    }
    const contentElement = noteElement.querySelector(':scope > ' + NOTE_CONTENT_SELECTOR);
    if (!contentElement) {
        noteElement.dataset[CAN_COLLAPSE_DATA_KEY] = 'false';
        return;
    }

    const hasMetaCsv = Boolean(contentElement.querySelector(META_CSV_SELECTOR));
    const isCollapsed = noteElement.dataset[COLLAPSED_DATA_KEY] === 'true';

    // Determine collapsibility based on the *expanded* layout.
    // A note should not become "collapsible" merely because it is marked collapsed.
    // This keeps bulk-collapse operations from introducing toggles on short notes.
    const hadCollapsedClass = noteElement.classList.contains('collapsed');
    if (hadCollapsedClass) {
        noteElement.classList.remove('collapsed');
    }
    const statusPreviewState = syncCollapsedStatusPreview(contentElement, false);

    let canCollapse = false;
    if (hasChildren(noteElement)) {
        canCollapse = true;
    } else if (hasMetaCsv) {
        canCollapse = true;
    } else if (statusPreviewState) {
        canCollapse = statusPreviewState.hasAdditionalLines;
    } else if (contentHasAdditionalLines(contentElement)) {
        canCollapse = true;
    }

    noteElement.dataset[CAN_COLLAPSE_DATA_KEY] = canCollapse ? 'true' : 'false';
    const shouldApplyCollapsedClass = isCollapsed && canCollapse;

    // Ensure the DOM class matches the dataset for consistent styling.
    if (shouldApplyCollapsedClass) {
        noteElement.classList.add('collapsed');
    } else {
        noteElement.classList.remove('collapsed');
    }
    syncCollapsedStatusPreview(contentElement, shouldApplyCollapsedClass);

    const collapseToggle = noteElement.querySelector(':scope > .note-collapse-toggle');
    if (collapseToggle) {
        collapseToggle.setAttribute('aria-label', shouldApplyCollapsedClass ? 'Expand note' : 'Collapse note');
        collapseToggle.removeAttribute('title');
    }

    refreshAffordanceAfterPendingImagesLoad(noteElement, contentElement);
}

export function setNoteCollapsedLocally(noteElement, collapsed) {
    if (!(noteElement instanceof HTMLElement) || !noteElement.classList.contains('note')) {
        throw new Error('setNoteCollapsedLocally requires note element');
    }
    if (typeof collapsed !== 'boolean') {
        throw new Error('setNoteCollapsedLocally requires collapsed boolean');
    }

    noteElement.dataset[COLLAPSED_DATA_KEY] = collapsed ? 'true' : 'false';
    updateCollapseAffordanceForNote(noteElement);
}

export function ensureNoteExpandedLocally(noteId) {
    if (!noteId) {
        throw new Error('ensureNoteExpandedLocally requires a noteId');
    }

    const noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
    if (!noteElement) {
        throw new Error(`Cannot ensure local expanded state: note ${noteId} not found`);
    }

    setNoteCollapsedLocally(noteElement, false);
}

export async function ensureNoteExpanded(noteId) {
    if (!noteId) {
        throw new Error('ensureNoteExpanded requires a noteId');
    }

    const noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
    if (!noteElement) {
        throw new Error(`Cannot ensure expanded state: note ${noteId} not found`);
    }

    const isCollapsed = noteElement.dataset[COLLAPSED_DATA_KEY] === 'true';
    if (!isCollapsed) {
        return;
    }

    await NotesAPI.expandNote(noteId);
    noteElement.dataset[COLLAPSED_DATA_KEY] = 'false';
    noteElement.classList.remove('collapsed');

    updateCollapseAffordanceForNote(noteElement);
}
