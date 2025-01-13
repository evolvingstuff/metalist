import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';
import { DOMUtils } from '../../dom-utils.js';

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
        // Clear any previous context
        return null;
    },

    exit: async () => {
        // Nothing to clean up
    },

    handleEvent: async (stateMachineEvent) => {
        if (!stateMachineEvent) {
            throw new Error('Idle state received null/undefined event');
        }

        const { type, context } = stateMachineEvent;
        if (!type) {
            throw new Error('Event missing type');
        }

        if (type === 'NOTE_CONTENT_CLICKED') {
            if (!context) {
                throw new Error('Note click missing context');
            }
            if (!(context instanceof StateContext)) {
                throw new Error('Invalid context: must be StateContext instance');
            }

            console.log('Handling note click in idle:', context);
            return {
                type: 'START_EDITING',
                context
            };
        }

        if (type === 'CREATE_TOP_NOTE') {
            const result = await NotesAPI.createNote();
            if (!result?.id) {
                throw new Error('Failed to create note - missing ID in response');
            }

            return {
                type: 'START_EDITING',
                context: StateContext.fromStateData({
                    noteId: result.id,
                    cursorOffset: 0
                })
            };
        }

        if (type === 'ENTER_PRESSED' || type === 'COMMAND_ENTER_PRESSED') {
            const result = await NotesAPI.createNote();
            if (!result?.id) {
                throw new Error('Failed to create note - missing ID in response');
            }

            // Note: We trust the API response and don't check DOM
            // The view layer will handle showing the new note
            return {
                type: 'START_EDITING',
                context: StateContext.fromStateData({
                    noteId: result.id,
                    cursorOffset: 0
                })
            };
        }

        if (type === 'KEY_DOWN') {
            const { key, metaKey, shiftKey } = stateMachineEvent;

            if (key === '/') {
                return { type: 'START_SEARCHING' };
            }

            // All other keys are ignored in idle state
            return context;  // No changes needed
        }

        if (type === 'SEARCH_FOCUSED') {
            return { type: 'START_SEARCHING' };
        }

        if (type === 'CLICKED_OUTSIDE_NOTE') {
            return context;
        }

        if (type === 'FRAGMENT_LOADED') {
            // Fragment loaded events are handled by updating the DOM
            // No state transition needed
            return context;
        }

        throw new Error(`Unknown event type: ${type}`);
    }
}; 