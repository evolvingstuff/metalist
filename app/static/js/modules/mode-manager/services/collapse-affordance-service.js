import { NotesAPI } from '../../api-client.js';

const NOTE_SELECTOR = '.note';
const NOTE_CONTENT_SELECTOR = '.note-content';
const COLLAPSED_DATA_KEY = 'isCollapsed';
const CAN_COLLAPSE_DATA_KEY = 'canCollapse';
const MULTILINE_HEIGHT_TOLERANCE = 1.35;

function parsePixelValue(value) {
    if (typeof value !== 'string') {
        throw new Error('parsePixelValue requires a string');
    }
    if (!value.endsWith('px')) {
        return null;
    }
    const numeric = Number.parseFloat(value);
    if (!Number.isFinite(numeric)) {
        throw new Error(`Invalid CSS pixel value: ${value}`);
    }
    return numeric;
}

function resolveLineHeightPx(contentElement) {
    if (!contentElement) {
        throw new Error('resolveLineHeightPx requires content element');
    }
    if (!globalThis.window || typeof globalThis.window.getComputedStyle !== 'function') {
        throw new Error('window.getComputedStyle is required for collapse affordance measurement');
    }

    const styles = globalThis.window.getComputedStyle(contentElement);
    const lineHeight = parsePixelValue(styles.lineHeight);
    if (lineHeight !== null) {
        return lineHeight;
    }

    const fontSize = parsePixelValue(styles.fontSize);
    if (fontSize === null) {
        throw new Error(`Cannot resolve collapse line height from font-size: ${styles.fontSize}`);
    }
    return fontSize * 1.2;
}

export function doesRenderedContentNeedCollapse(contentElement) {
    if (!contentElement) {
        throw new Error('doesRenderedContentNeedCollapse requires content element');
    }

    const lineHeightPx = resolveLineHeightPx(contentElement);
    const rect = contentElement.getBoundingClientRect();
    if (!rect || typeof rect.height !== 'number') {
        throw new Error('content element must provide a bounding rect height');
    }
    if (typeof contentElement.scrollHeight !== 'number') {
        throw new Error('content element must provide scrollHeight');
    }

    const measuredHeight = Math.max(rect.height, contentElement.scrollHeight);
    return measuredHeight > lineHeightPx * MULTILINE_HEIGHT_TOLERANCE;
}

export function resolveCanCollapseFromDataset(dataset) {
    if (!dataset) {
        throw new Error('resolveCanCollapseFromDataset requires dataset');
    }
    return dataset.isCollapsible === 'true';
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

    const isCollapsed = noteElement.dataset[COLLAPSED_DATA_KEY] === 'true';
    const isSearchRedacted = noteElement.dataset.searchRedacted === 'true';
    const serverCanCollapse = resolveCanCollapseFromDataset(noteElement.dataset);
    const wasCollapsed = noteElement.classList.contains('collapsed');
    if (wasCollapsed) {
        noteElement.classList.remove('collapsed');
    }
    const renderedContentNeedsCollapse = doesRenderedContentNeedCollapse(contentElement);
    if (wasCollapsed) {
        noteElement.classList.add('collapsed');
    }
    const canCollapse = !isSearchRedacted && (serverCanCollapse || renderedContentNeedsCollapse);

    noteElement.dataset[CAN_COLLAPSE_DATA_KEY] = canCollapse ? 'true' : 'false';
    const shouldApplyCollapsedClass = isCollapsed && canCollapse;

    // Ensure the DOM class matches the dataset for consistent styling.
    if (shouldApplyCollapsedClass) {
        noteElement.classList.add('collapsed');
    } else {
        noteElement.classList.remove('collapsed');
    }

    const collapseToggle = noteElement.querySelector(':scope > .note-collapse-toggle');
    if (collapseToggle) {
        collapseToggle.setAttribute('aria-label', shouldApplyCollapsedClass ? 'Expand note' : 'Collapse note');
        collapseToggle.removeAttribute('title');
    }
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
