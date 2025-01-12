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

        if (type === 'CLICK_OUTSIDE_NOTE') {
            return null;
        }

        if (type === 'CREATE_TOP_NOTE') {
            const result = await NotesAPI.createNote();
            if (!result) {
                throw new Error('Failed to create note');
            }

            const newNote = document.querySelector(`[data-id="${result.id}"]`);
            if (!newNote) {
                throw new Error('Created note not found in DOM');
            }

            return {
                type: 'START_EDITING',
                data: {
                    nextNote: newNote,
                    cursorPosition: 'end'
                }
            };
        }

        if (type === 'ENTER_PRESSED' || type === 'COMMAND_ENTER_PRESSED') {
            const result = await NotesAPI.createNote();
            if (!result) {
                throw new Error('Failed to create note');
            }

            const newNote = document.querySelector(`[data-id="${result.id}"]`);
            if (!newNote) {
                throw new Error('Created note not found in DOM');
            }

            return {
                type: 'START_EDITING',
                data: {
                    nextNote: newNote,
                    cursorPosition: 'end'
                }
            };
        }

        return null;
    }
}; 