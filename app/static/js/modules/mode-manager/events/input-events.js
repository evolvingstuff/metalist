import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { actionSelectNote } from '../actions/selection-actions.js';
import { DOMUtils } from '../../dom-utils.js';

export function initInputEvents() {
        
    document.addEventListener('input', handleInput, { capture: true });
        
    Logger.logInit('Input events handler');
}

function handleInput(event) {
    if (!event) {
        throw new Error('handleInput called without an event object');
    }
        
    if (!event.target) {
        throw new Error('Input event missing target element');
    }

    if (ModeContext.isLoading) {
        Logger.logNoop('Input event ignored while system is loading', {
            targetElement: event.target.tagName,
            targetValue: event.target.value?.length,
            isLoading: true
        });
        event.preventDefault();
        return;
    }
        
    const noteContent = event.target.closest('.note-content');
        
    if (noteContent) {
        const noteElement = noteContent.closest('.note');
        if (!noteElement) {
            throw new Error('Found .note-content without parent .note element in input handler');
        }
                
        const noteId = noteElement.dataset.noteId;
        if (!noteId) {
            throw new Error('Note element missing data-note-id attribute in input handler');
        }

        if (!ModeContext.isEditing || ModeContext.currentNoteId !== noteId) {
            actionSelectNote(noteId);
            return; 
        }

        const currentHtmlContent = DOMUtils.getNoteContentHTML(noteElement);

        if (currentHtmlContent !== ModeContext.currentContent) {
                        
            ModeContext.setCurrentContent(currentHtmlContent);

            if (!ModeContext.isDirty) {
                ModeContext.setDirty(true);
                Logger.logDebug('Content marked as dirty due to typing', { 
                    key: event.data, 
                    noteId 
                }, Logger.LogCategory.STATE);
            }
                        
            Logger.logDebug('Note content changed', { 
                noteId,
                contentLength: currentHtmlContent.length
            }, Logger.LogCategory.EVENT);
        }
    } 
    // Search input handling is now done by search-events.js
}