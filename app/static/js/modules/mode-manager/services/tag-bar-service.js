import { CONFIG } from '../../config.js';
import { analyzeTagBarInput, enforceTagBarInputForEditing, normalizeTagBarInput } from './tag-syntax-service.js';

const TAG_BAR_CLASS = 'note-tag-bar';
const TAG_BAR_INPUT_CLASS = 'note-tag-bar-input';
const TAG_BAR_VALIDATION_MESSAGE_CLASS = 'note-tag-bar-validation-message';

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
        return { element: existing, created: false };
    }

    const tagBar = document.createElement('div');
    tagBar.classList.add(TAG_BAR_CLASS);

    const validationMessage = document.createElement('div');
    validationMessage.classList.add(TAG_BAR_VALIDATION_MESSAGE_CLASS);
    validationMessage.hidden = true;
    tagBar.appendChild(validationMessage);

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

    return { element: tagBar, created: true };
}

function ensureValidationMessageElement(tagBar) {
    if (!tagBar) {
        return null;
    }

    const existing = tagBar.querySelector(`.${TAG_BAR_VALIDATION_MESSAGE_CLASS}`);
    if (existing) {
        return existing;
    }

    const validationMessage = document.createElement('div');
    validationMessage.classList.add(TAG_BAR_VALIDATION_MESSAGE_CLASS);
    validationMessage.hidden = true;
    tagBar.insertBefore(validationMessage, tagBar.firstChild);
    return validationMessage;
}

function setTagBarValidationState(tagBar, analysis) {
    if (!tagBar) {
        throw new Error('setTagBarValidationState requires a tag bar element');
    }
    if (!analysis || typeof analysis.isValid !== 'boolean') {
        throw new Error('setTagBarValidationState requires an analysis result');
    }

    const validationMessage = ensureValidationMessageElement(tagBar);
    if (analysis.isValid) {
        if (validationMessage) {
            validationMessage.hidden = true;
            validationMessage.textContent = '';
        }
        return;
    }

    if (!validationMessage) {
        return;
    }

    if (typeof analysis.errorMessage !== 'string') {
        throw new Error('Invariant violation: invalid tag bar state missing errorMessage');
    }
    validationMessage.textContent = analysis.errorMessage;
    validationMessage.hidden = false;
}

export function enforceTagBarInputElement(tagBarInput) {
    if (!tagBarInput) {
        throw new Error('enforceTagBarInputElement requires an input element');
    }

    const rawValue = typeof tagBarInput.value === 'string' ? tagBarInput.value : '';
    const enforcedValue = enforceTagBarInputForEditing(rawValue);
    if (enforcedValue === rawValue) {
        return false;
    }

    const selectionStart = Number.isInteger(tagBarInput.selectionStart) ? tagBarInput.selectionStart : rawValue.length;
    const selectionEnd = Number.isInteger(tagBarInput.selectionEnd) ? tagBarInput.selectionEnd : selectionStart;

    const nextSelectionStart = enforceTagBarInputForEditing(rawValue.slice(0, selectionStart)).length;
    const nextSelectionEnd = enforceTagBarInputForEditing(rawValue.slice(0, selectionEnd)).length;

    tagBarInput.value = enforcedValue;
    if (typeof tagBarInput.setSelectionRange === 'function') {
        tagBarInput.setSelectionRange(nextSelectionStart, nextSelectionEnd);
    }

    return true;
}

function getTagBarInput(tagBar) {
    if (!tagBar) {
        return null;
    }
    return tagBar.querySelector(`.${TAG_BAR_INPUT_CLASS}`);
}

function isTagBarFocused(tagBar) {
    const input = getTagBarInput(tagBar);
    if (!input) {
        return false;
    }
    return document.activeElement === input;
}

export function normalizeTags(rawTags) {
    if (typeof rawTags !== 'string') {
        throw new Error('normalizeTags expects a string');
    }
    return normalizeTagBarInput(rawTags);
}

export function sanitizeTags(rawTags) {
    if (typeof rawTags !== 'string') {
        throw new Error('sanitizeTags expects a string');
    }
    return analyzeTagBarInput(rawTags).sanitizedText;
}

export function normalizeTagBarForNewTag(noteElement, tagBarInput) {
    if (!noteElement) {
        throw new Error('normalizeTagBarForNewTag requires a note element');
    }
    if (!tagBarInput) {
        throw new Error('normalizeTagBarForNewTag requires a tag bar input element');
    }

    const inputValue = typeof tagBarInput.value === 'string' ? tagBarInput.value : '';
    const storedTags = typeof noteElement.dataset.noteTags === 'string' ? noteElement.dataset.noteTags : '';
    const existingTags = inputValue.length > 0 ? inputValue : storedTags;
    const normalized = normalizeTags(existingTags);
    const nextValue = normalized.length > 0 ? `${normalized} ` : '';

    tagBarInput.value = nextValue;
    const end = nextValue.length;
    if (typeof tagBarInput.setSelectionRange === 'function') {
        tagBarInput.setSelectionRange(end, end);
    }

    return nextValue;
}

export function validateAndRenderTagBar(noteElement) {
    if (!noteElement) {
        throw new Error('validateAndRenderTagBar requires a note element');
    }

    const tagBar = getDirectChildByClass(noteElement, TAG_BAR_CLASS);
    const input = getTagBarInput(tagBar);
    if (!tagBar || !input || typeof input.value !== 'string') {
        return null;
    }

    const analysis = analyzeTagBarInput(input.value);
    setTagBarValidationState(tagBar, analysis);
    return analysis;
}

export function getTagBarValue(noteElement) {
    if (!noteElement) {
        throw new Error('getTagBarValue requires a note element');
    }
    const tagBar = getDirectChildByClass(noteElement, TAG_BAR_CLASS);
    const input = getTagBarInput(tagBar);
    if (input && typeof input.value === 'string') {
        return analyzeTagBarInput(input.value).sanitizedText;
    }
    const storedTags = typeof noteElement.dataset.noteTags === 'string' ? noteElement.dataset.noteTags : '';
    return analyzeTagBarInput(storedTags).sanitizedText;
}

export function setTagBarValue(noteElement, tags) {
    if (!noteElement) {
        throw new Error('setTagBarValue requires a note element');
    }
    if (typeof tags !== 'string') {
        throw new Error('setTagBarValue requires tags string');
    }
    const normalized = normalizeTagBarInput(tags);
    noteElement.dataset.noteTags = normalized;
    const tagBar = getDirectChildByClass(noteElement, TAG_BAR_CLASS);
    const input = getTagBarInput(tagBar);
    if (input) {
        input.value = normalized;
    }

    if (tagBar) {
        setTagBarValidationState(tagBar, analyzeTagBarInput(normalized));
    }
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
    const tagBarResult = ensureTagBarElement(editingNoteElement);
    const tagBar = tagBarResult.element;

    if (tagBarResult.created) {
        const initialTags = typeof editingNoteElement.dataset.noteTags === 'string'
            ? editingNoteElement.dataset.noteTags
            : '';
        setTagBarValue(editingNoteElement, initialTags);
    }

    validateAndRenderTagBar(editingNoteElement);

    // Keep the tag bar in the DOM while focused so typing can trigger the
    // global input handler (used for scroll restoration during editing).
    tagBar.hidden = !isTagBarFocused(tagBar) && !isElementPartiallyInViewport(editingNoteElement);

    if (typeof IntersectionObserver !== 'undefined') {
        if (activeObserver) {
            return;
        }
        activeObserver = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (entry.target !== editingNoteElement) {
                    continue;
                }
                tagBar.hidden = !isTagBarFocused(tagBar) && !entry.isIntersecting;
            }
        });
        activeObserver.observe(editingNoteElement);
        return;
    }

    if (!activeFallbackHandler) {
        activeFallbackHandler = () => {
            tagBar.hidden = !isTagBarFocused(tagBar) && !isElementPartiallyInViewport(editingNoteElement);
        };
        window.addEventListener('scroll', activeFallbackHandler, true);
        window.addEventListener('resize', activeFallbackHandler);
    }
}

export function clearTagBar() {
    syncTagBar(null);
}
