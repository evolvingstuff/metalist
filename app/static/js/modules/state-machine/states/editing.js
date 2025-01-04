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
        const { nextNote, cursorPosition } = data;
        
        // Set up note for editing
        DOMUtils.setNoteEditable(nextNote, true);
        
        // Handle cursor position based on context
        if (cursorPosition === 'end') {
            DOMUtils.focusNote(nextNote);
        } else if (cursorPosition) {
            DOMUtils.setCursorPosition(nextNote, cursorPosition);
        }

        return {
            currentNote: nextNote,
            lastSavedContent: DOMUtils.getNoteContentText(nextNote),
            currentContent: DOMUtils.getNoteContentText(nextNote)
        };
    },

    exit: async (data, nextState) => {
        const { currentNote, lastSavedContent } = data;
        
        // Save if content changed
        const currentContent = DOMUtils.getNoteContentText(currentNote);
        if (currentContent !== lastSavedContent) {
            await NotesAPI.updateNote(
                DOMUtils.getNoteId(currentNote), 
                currentContent
            );
        }

        // Clean up note
        DOMUtils.setNoteEditable(currentNote, false);

        return {};  // Clear temporary editing state
    }
}; 