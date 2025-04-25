import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { selectNote } from '../actions/selection-actions.js';
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
        
    const noteContent = event.target.closest('.note-content');
    const searchField = event.target.closest('#search-input');
        
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
            selectNote(noteId);
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
    } else if (searchField) {
        if (searchField.value === undefined) {
            throw new Error('Search field has no value property');
        }
                
        const searchQuery = searchField.value;
        ModeContext.setSearchQuery(searchQuery);
        ModeContext.setSearching(true);
        ModeContext.validate();
                
        Logger.logDebug('Search query changed', { query: searchQuery }, Logger.LogCategory.EVENT);
    }
}