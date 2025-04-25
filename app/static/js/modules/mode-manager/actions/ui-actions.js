import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';

export async function refresh(options = {}) {
    Logger.logAction('refresh', { 
        noteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing
    });

    const noteId = ModeContext.currentNoteId;

    const shouldManageLoading = !options.skipLoadingState;
    if (shouldManageLoading && !ModeContext.isLoading) {
        ModeContext.setLoading(true);
    }

    const html = await NotesAPI.getFragment(noteId);

    const notesContainer = document.getElementById('notes-container');
    if (!notesContainer) {
        throw new Error('Notes container not found');
    }
        
    notesContainer.innerHTML = html;

    if (noteId) {
        const noteElement = DOMUtils.getNoteById(noteId);
        const contentHtml = DOMUtils.getNoteContentHTML(noteElement);

        ModeContext.setCurrentContent(contentHtml);

        if (ModeContext.isEditing) {
                        
            DOMUtils.setNoteEditable(noteElement, true);

            let cursorOffset = 0;
                        
            if (ModeContext._savedCursorOffset && ModeContext._savedCursorOffset.noteId === noteId) {
                                
                cursorOffset = ModeContext._savedCursorOffset.offset;

                ModeContext._savedCursorOffset = null;
                                
                Logger.logDebug('Using stored cursor offset', {
                    cursorOffset
                }, Logger.LogCategory.DEBUG);
            } else {
                                
                const contentElement = DOMUtils.getNoteContent(noteElement);
                cursorOffset = contentElement.textContent.length || 0;
            }

            DOMUtils.focusNote(noteElement, cursorOffset);
        }

        if (shouldManageLoading && ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
                
        return contentHtml;
    } else {
                
        if (shouldManageLoading && ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
                
        return html;
    }
}

export async function loadNote(noteId) {
    Logger.logAction('loadNote', { noteId });

    if (!noteId) {
        throw new Error('Cannot load note: noteId is required');
    }

    return await refresh({ noteId });
}