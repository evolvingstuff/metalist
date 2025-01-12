import { NotesAPI } from '../../api-client.js';

/**
 * Idle State
 * 
 * Default application state when no active interactions.
 * Serves as the base state for transitions to editing/searching.
 * 
 * State Data:
 * - No persistent data
 * 
 * Transitions:
 * - Enter: Cleans up any leftover state
 * - Exit: No specific cleanup needed
 * 
 * @example
 * // Return to idle state
 * await transition('idle');
 */

export const idleTransitions = {
    enter: async (data, prevState) => {
        // Clean slate when entering idle
        return {};
    },

    exit: async (data, nextState) => {
        // No cleanup needed
        return {};
    },

    handleEvent: async (event) => {
        const { type } = event;

        if (type === 'KEY_DOWN') {
            const { key, metaKey } = event;

            if (key === '/') {
                return { type: 'START_SEARCHING' };
            }

            // All other keys are ignored in idle state
            return { type: 'NO_OP' };
        }

        if (type === 'CLICKED_OUTSIDE_NOTE') {
            return { type: 'NO_OP' };
        }

        if (type === 'NOTE_CONTENT_CLICKED') {
            const { noteElement, position } = event.data;
            const noteId = DOMUtils.getNoteId(noteElement);
            if (!noteId) {
                throw new Error('Note click missing noteId');
            }

            console.log('Handling note click in idle:', { noteElement, noteId, position });
            return {
                type: 'START_EDITING',
                data: {
                    noteId,  
                    cursorPosition: position
                }
            };
        }

        if (type === 'CREATE_TOP_NOTE') {
            const result = await NotesAPI.createNote();
            if (!result?.id) {
                throw new Error('Failed to create note - missing ID in response');
            }

            // Wait for DOM to update
            const newNote = document.querySelector(`[data-id="${result.id}"]`);
            if (!newNote) {
                throw new Error('Created note not found in DOM');
            }

            return {
                type: 'START_EDITING',
                data: {
                    noteId: result.id,  
                    cursorPosition: 'end'
                }
            };
        }

        if (type === 'ENTER_PRESSED' || type === 'COMMAND_ENTER_PRESSED') {
            const result = await NotesAPI.createNote();
            if (!result?.id) {
                throw new Error('Failed to create note - missing ID in response');
            }

            // Wait for DOM to update
            const newNote = document.querySelector(`[data-id="${result.id}"]`);
            if (!newNote) {
                throw new Error('Created note not found in DOM');
            }

            return {
                type: 'START_EDITING',
                data: {
                    noteId: result.id,  
                    cursorPosition: 'end'
                }
            };
        }

        if (type === 'FRAGMENT_LOADED') {
            // Fragment loaded events are handled by updating the DOM
            // No state transition needed
            return { type: 'NO_OP' };
        }

        throw new Error(`Unhandled event type: ${type}`);
    }
}; 