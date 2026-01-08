import { CONFIG } from '../../config.js';

const TAG_BAR_CLASS = 'note-tag-bar';
const TAG_BAR_INPUT_CLASS = 'note-tag-bar-input';

let activeNoteElement = null;
let activeObserver = null;
let activeFallbackHandler = null;

function getDirectChildByClass(parent, className) {
    for (const child of Array.from(parent.children)) {
        if (child.classList && child.classList.contains(className)) {
            return child;
        }
    }
    return null;
}

function isElementPartiallyInViewport(element) {
    const rect = element.getBoundingClientRect();
    return rect.bottom > 0
        && rect.top < window.innerHeight
        && rect.right > 0
        && rect.left < window.innerWidth;
}

function ensureTagBarElement(noteElement) {
    const existing = getDirectChildByClass(noteElement, TAG_BAR_CLASS);
    if (existing) {
        return existing;
    }

    const tagBar = document.createElement('div');
    tagBar.classList.add(TAG_BAR_CLASS);

    const input = document.createElement('input');
    input.classList.add(TAG_BAR_INPUT_CLASS);
    input.type = 'text';
    input.placeholder = 'tags';
    input.autocomplete = 'off';
    input.spellcheck = false;

    tagBar.appendChild(input);

    const contentElement = getDirectChildByClass(noteElement, CONFIG.CLASSES.NOTE_CONTENT);
    const childContainer = getDirectChildByClass(noteElement, 'note-children');

    if (!contentElement) {
        throw new Error('Cannot attach tag bar: note missing direct note-content child');
    }

    if (childContainer) {
        noteElement.insertBefore(tagBar, childContainer);
    } else if (contentElement.nextSibling) {
        noteElement.insertBefore(tagBar, contentElement.nextSibling);
    } else {
        noteElement.appendChild(tagBar);
    }

    return tagBar;
}

function removeTagBar(noteElement) {
    const existing = getDirectChildByClass(noteElement, TAG_BAR_CLASS);
    if (existing) {
        existing.remove();
    }
}

function disconnectVisibilityTracking() {
    if (activeObserver) {
        activeObserver.disconnect();
        activeObserver = null;
    }

    if (activeFallbackHandler) {
        window.removeEventListener('scroll', activeFallbackHandler, true);
        window.removeEventListener('resize', activeFallbackHandler);
        activeFallbackHandler = null;
    }
}

function isEditingByMe(noteElement) {
    const isEditing = noteElement.classList.contains(CONFIG.CLASSES.EDITING);
    if (!isEditing) {
        return false;
    }

    const contentElement = noteElement.querySelector(`:scope > .${CONFIG.CLASSES.NOTE_CONTENT}`)
        || noteElement.querySelector(`.${CONFIG.CLASSES.NOTE_CONTENT}`);
    if (!contentElement) {
        throw new Error('Cannot determine edit state: note missing content element');
    }
    return contentElement.getAttribute('contenteditable') === 'true';
}

export function syncTagBar(editingNoteElement) {
    if (!editingNoteElement || !isEditingByMe(editingNoteElement)) {
        if (activeNoteElement) {
            disconnectVisibilityTracking();
            removeTagBar(activeNoteElement);
            activeNoteElement = null;
        }
        return;
    }

    if (activeNoteElement && activeNoteElement !== editingNoteElement) {
        disconnectVisibilityTracking();
        removeTagBar(activeNoteElement);
        activeNoteElement = null;
    }

    activeNoteElement = editingNoteElement;
    const tagBar = ensureTagBarElement(editingNoteElement);

    tagBar.hidden = !isElementPartiallyInViewport(editingNoteElement);

    if (typeof IntersectionObserver !== 'undefined') {
        if (activeObserver) {
            return;
        }
        activeObserver = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (entry.target !== editingNoteElement) {
                    continue;
                }
                tagBar.hidden = !entry.isIntersecting;
            }
        });
        activeObserver.observe(editingNoteElement);
        return;
    }

    if (!activeFallbackHandler) {
        activeFallbackHandler = () => {
            tagBar.hidden = !isElementPartiallyInViewport(editingNoteElement);
        };
        window.addEventListener('scroll', activeFallbackHandler, true);
        window.addEventListener('resize', activeFallbackHandler);
    }
}

export function clearTagBar() {
    syncTagBar(null);
}
