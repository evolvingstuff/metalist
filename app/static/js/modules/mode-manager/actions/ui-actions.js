import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';
import { CONFIG } from '../../config.js';
import { highlightCommentsOnRender } from '../events/input-events.js';

export async function actionRefreshAndMaybeSelect(options = {}) {
    Logger.logAction('refresh_and_maybe_select', { 
        noteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing
    });

    const noteId = ModeContext.currentNoteId;

    const shouldManageLoading = !options.skipLoadingState;
    if (shouldManageLoading && !ModeContext.isLoading) {
        ModeContext.setLoading(true);
    }

    const html = await NotesAPI.fetchView(noteId, ModeContext.searchQuery);

    const notesContainer = document.getElementById('notes-container');
    if (!notesContainer) {
        throw new Error('Notes container not found');
    }
    
    // Update content directly - app-level fade handles the transition
    notesContainer.innerHTML = html;
    
    // If this is initial page load, fade in the entire app
    if (ModeContext.isInitialPageLoad) {
        const appContainer = document.getElementById('app');
        if (appContainer) {
            appContainer.classList.add('loaded');
        }
        ModeContext.markInitialPageLoadComplete();
    }

    let contentHtml = null;
    
    if (noteId) {
        const noteElement = DOMUtils.getNoteById(noteId);
        contentHtml = DOMUtils.getNoteContentHTML(noteElement);

        if (ModeContext.isEditing) {
                        
            DOMUtils.setNoteEditable(noteElement, true);
            
            // Highlight comments immediately when entering edit mode
            const noteContentElement = DOMUtils.getNoteContent(noteElement);
            highlightCommentsOnRender(noteContentElement);

            let cursorOffset = 0;
                        
            const savedOffset = ModeContext.savedCursorOffset;
            if (savedOffset && savedOffset.noteId === noteId) {
                                
                cursorOffset = savedOffset.offset;

                ModeContext.clearSavedCursorOffset();
                                
                Logger.logDebug('Using stored cursor offset', {
                    cursorOffset
                }, Logger.LogCategory.DEBUG);
            } else {
                // Use configured default cursor position when no saved offset
                const contentElement = DOMUtils.getNoteContent(noteElement);
                if (CONFIG.EDITOR.DEFAULT_CURSOR_POSITION === 'END') {
                    cursorOffset = contentElement.textContent.length || 0;
                } else {
                    // Default to START
                    cursorOffset = 0;
                }
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
