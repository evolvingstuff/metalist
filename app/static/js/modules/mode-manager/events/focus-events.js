import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { normalizeTags, setTagBarValue } from '../services/tag-bar-service.js';

export function initFocusEvents() {
        
    document.addEventListener('focusin', handleFocus, { capture: true });
    document.addEventListener('focusout', handleBlur, { capture: true });
        
    Logger.logInit('Focus events handler (search only)');
}

function handleFocus(event) {
    if (!event) {
        throw new Error('handleFocus called without an event object');
    }
        
    if (!event.target) {
        throw new Error('Focus event missing target element');
    }

    if (ModeContext.isLoading) {
        Logger.logNoop('Focus event ignored while system is loading', {
            targetElement: event.target.tagName,
            isLoading: true
        });
        return;
    }
        
    const searchField = event.target.closest('#search-input');
        
    if (searchField) {

        Logger.logDebug('Search field focused (no state change)');
    }
}

function handleBlur(event) {
    if (!event) {
        throw new Error('handleBlur called without an event object');
    }
        
    if (!event.target) {
        throw new Error('Blur event missing target element');
    }

    if (ModeContext.isLoading) {
        Logger.logNoop('Blur event ignored while system is loading', {
            targetElement: event.target.tagName,
            isLoading: true
        });
        return;
    }
        
    const searchField = event.target.closest('#search-input');
    const tagBarInput = event.target.closest('.note-tag-bar-input');
        
    if (searchField) {

        Logger.logDebug('Search field blurred (no state change)');
    }

    if (tagBarInput) {
        const noteElement = tagBarInput.closest('.note');
        if (!noteElement) {
            throw new Error('Found tag bar input without parent note element');
        }

        const noteId = noteElement.dataset?.noteId;
        if (!noteId) {
            throw new Error('Tag bar note element missing data-note-id');
        }

        if (!ModeContext.isEditing || ModeContext.currentNoteId !== noteId) {
            return;
        }

        const normalized = normalizeTags(tagBarInput.value || '');
        setTagBarValue(noteElement, normalized);
    }
}
