import { DOMUtils } from '../../dom-utils.js';
import { NotesAPI } from '../../api-client.js';

/**
 * Editing State
 * 
 * Manages note editing functionality including:
 * - Setting up editable notes
 * - Cursor position management
 * - Content change tracking
 * - Auto-saving
 * 
 * State Data:
 * - currentNote: Currently edited note element
 * - lastSavedContent: Content at last save
 * - currentContent: Current note content
 * 
 * Transitions:
 * - Enter: Sets up note for editing, manages focus
 * - Exit: Saves changes, cleans up editable state
 * 
 * @example
 * // Enter editing state
 * await transition('editing', {
 *   nextNote: noteElement,
 *   cursorPosition: 'end'
 * });
 */

export const editingTransitions = {
    enter: async (data, prevState) => {
        const { nextNote, cursorPosition, activityMonitor } = data;
        
        // Set up note for editing
        DOMUtils.setNoteEditable(nextNote, true);
        
        // Handle cursor position based on context
        if (cursorPosition === 'end') {
            DOMUtils.focusNote(nextNote);
        } else if (cursorPosition) {
            DOMUtils.setCursorPosition(nextNote, cursorPosition);
        }

        // Start activity monitoring
        activityMonitor?.startMonitoring();

        return {
            currentNote: nextNote,
            lastSavedContent: DOMUtils.getNoteContentText(nextNote),
            currentContent: DOMUtils.getNoteContentText(nextNote)
        };
    },

    exit: async (data, nextState) => {
        const { currentNote, lastSavedContent, activityMonitor } = data;
        
        // Stop activity monitoring
        activityMonitor?.stopMonitoring();
        
        // Save if content changed
        const currentContent = DOMUtils.getNoteContentText(currentNote);
        if (currentContent !== lastSavedContent) {
            console.log(' [EDITING EXIT] Saving content changes:', {
                noteId: DOMUtils.getNoteId(currentNote),
                lastSavedContent,
                currentContent
            });
            await NotesAPI.saveNote(
                DOMUtils.getNoteId(currentNote), 
                currentContent
            );
            console.log(' [EDITING EXIT] Content saved');
        }

        // Clear selection for the current note only
        const contentElement = DOMUtils.getNoteContent(currentNote);
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            if (contentElement.contains(range.commonAncestorContainer)) {
                selection.removeAllRanges();
            }
        }

        // Clean up note
        DOMUtils.setNoteEditable(currentNote, false);

        return {};  // Clear temporary editing state
    },

    handleEvent: async (event, data) => {
        const { type } = event;
        
        if (type === 'INACTIVITY_TIMEOUT') {
            const { currentNote, lastSavedContent } = data;
            const currentContent = DOMUtils.getNoteContentText(currentNote);
            
            // Only save if content has changed
            if (currentContent !== lastSavedContent) {
                console.log('⏰ [EDITING] Auto-saving on inactivity:', {
                    noteId: DOMUtils.getNoteId(currentNote),
                    lastSavedContent,
                    currentContent
                });
                
                NotesAPI.updateNote(
                    DOMUtils.getNoteId(currentNote), 
                    currentContent
                );
                
                return {
                    lastSavedContent: currentContent
                };
            }
        }
        
        return null;
    }
}; 