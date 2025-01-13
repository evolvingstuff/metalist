import { DOMUtils } from '../../dom-utils.js';
import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';

/**
 * Editing State
 * 
 * Manages note editing functionality including:
 * - Setting up editable notes
 * - Cursor position management
 * - Content change tracking
 * - Auto-saving
 * 
 * State Context:
 * - noteId: ID of currently edited note
 * - lastSavedContent: Content at last save
 * - cursorOffset: Cursor position in note
 * - activityMonitor: For tracking edit activity
 * 
 * Transitions:
 * - Enter: Sets up note for editing, manages focus
 * - Exit: Saves changes, cleans up editable state
 * 
 * @example
 * // Enter editing state
 * stateContext
 *   .setType('START_EDITING')
 *   .setNoteId('note-123')
 *   .setCursorOffset(10);
 */

export const editingTransitions = {
    enter: async (stateContext) => {
        if (!stateContext || !(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        const noteId = stateContext.getNoteId();
        if (!noteId) {
            throw new Error('Editing state requires note ID');
        }

        console.log(' Starting edit with context:', stateContext);
        
        // Start activity monitoring
        stateContext.getActivityMonitor()?.startMonitoring();

        // Set up note for editing
        const noteElement = DOMUtils.getNoteById(noteId);
        if (!noteElement) {
            throw new Error(`Could not find note element with ID: ${noteId}`);
        }

        // Make note editable
        DOMUtils.setNoteEditable(noteElement, true);

        // Set cursor position if specified
        const cursorOffset = stateContext.getCursorOffset();
        if (typeof cursorOffset === 'number') {
            DOMUtils.setCursorOffset(noteElement, cursorOffset);
        }

        return stateContext;
    },

    exit: async (stateContext) => {
        if (!stateContext || !(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        const noteId = stateContext.getNoteId();
        if (!noteId) {
            throw new Error('Cannot exit editing without note ID');
        }

        // Stop activity monitoring
        stateContext.getActivityMonitor()?.stopMonitoring();

        // Get current content
        const noteElement = DOMUtils.getNoteById(noteId);
        if (!noteElement) {
            throw new Error(`Could not find note element with ID: ${noteId}`);
        }
        const content = DOMUtils.getNoteContent(noteElement);

        // Save if content changed
        const lastSavedContent = stateContext.getLastSavedContent();
        if (content !== lastSavedContent) {
            await NotesAPI.updateNote(noteId, content);
            stateContext.setLastSavedContent(content);
        }

        // Clean up note
        DOMUtils.setNoteEditable(noteElement, false);

        return stateContext;
    },

    handleEvent: async (stateContext) => {
        if (!stateContext || !(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        const eventType = stateContext.getType();
        if (!eventType) {
            throw new Error('State context missing event type');
        }

        const noteId = stateContext.getNoteId();
        if (!noteId) {
            throw new Error('Editing state missing note ID');
        }

        console.log('Handling event in editing:', {
            type: eventType,
            context: stateContext
        });

        switch (eventType) {
            case 'NOTE_CONTENT_CLICKED': {
                const clickedNoteId = stateContext.getNoteId();
                if (clickedNoteId === noteId) {
                    // Clicked same note - do nothing
                    return stateContext;
                }

                // Get current content
                const noteElement = DOMUtils.getNoteById(clickedNoteId);
                if (!noteElement) {
                    throw new Error(`Could not find note element with ID: ${clickedNoteId}`);
                }
                const content = DOMUtils.getNoteContent(noteElement);

                // Switch to new note
                return stateContext
                    .setType('START_EDITING')
                    .setNoteId(clickedNoteId)
                    .setLastSavedContent(content);
            }

            case 'CLICKED_OUTSIDE_NOTE': {
                return stateContext.setType('START_IDLE');
            }

            case 'SEARCH_FOCUSED': {
                return stateContext.setType('START_SEARCHING');
            }

            default:
                console.log('Ignoring event in editing:', eventType);
                return stateContext;
        }
    }
};
