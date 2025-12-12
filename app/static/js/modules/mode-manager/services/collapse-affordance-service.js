import { NotesAPI } from '../../api-client.js';

const NOTE_SELECTOR = '.note';
const NOTE_CONTENT_SELECTOR = '.note-content';
const COLLAPSED_DATA_KEY = 'isCollapsed';
const CAN_COLLAPSE_DATA_KEY = 'canCollapse';
const DELTA_TOLERANCE = 1;

function parsePixels(value) {
    if (!value) {
        return 0;
    }
    const numeric = parseFloat(value);
    return Number.isFinite(numeric) ? numeric : 0;
}

function hasChildren(noteElement) {
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

export function updateCollapseAffordances(root = document) {
    const noteElements = root.querySelectorAll(NOTE_SELECTOR);
    noteElements.forEach(note => {
        const contentElement = note.querySelector(NOTE_CONTENT_SELECTOR);
        if (!contentElement) {
            note.dataset[CAN_COLLAPSE_DATA_KEY] = 'false';
            return;
        }

        const isCollapsed = note.dataset[COLLAPSED_DATA_KEY] === 'true';
        const canCollapse = isCollapsed || hasChildren(note) || contentHasAdditionalLines(contentElement);
        note.dataset[CAN_COLLAPSE_DATA_KEY] = canCollapse ? 'true' : 'false';

        // Ensure the DOM class matches the dataset for consistent styling.
        if (isCollapsed) {
            note.classList.add('collapsed');
        } else {
            note.classList.remove('collapsed');
        }

        const collapseToggle = note.querySelector(':scope > .note-collapse-toggle');
        if (collapseToggle) {
            collapseToggle.setAttribute('aria-label', isCollapsed ? 'Expand note' : 'Collapse note');
            collapseToggle.setAttribute('title', isCollapsed ? 'Expand' : 'Collapse');
        }
    });
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
}
