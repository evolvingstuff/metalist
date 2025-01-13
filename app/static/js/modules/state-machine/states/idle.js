import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';
import { DOMUtils } from '../../dom-utils.js';

/**
 * Idle State
 * 
 * Default application state when no active interactions.
 * Serves as the base state for transitions to editing/searching.
 * 
 * State Context:
 * - No persistent data needed
 * 
 * Transitions:
 * - Enter: Cleans up any leftover state
 * - Exit: No specific cleanup needed
 * 
 * @example
 * // Return to idle state
 * stateContext.setTargetState('idle');
 * await transition(stateContext);
 */

export const idleTransitions = {
    enter: async (stateContext) => {
        // Validate context
        if (!stateContext || !(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }
        
        // Nothing to set up
        return stateContext;
    },

    exit: async (stateContext) => {
        // Nothing to clean up
        return stateContext;
    },

    handleEvent: async (stateContext) => {
        // NO MERCY validation
        if (!stateContext || !(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        const eventType = stateContext.getType();
        if (!eventType) {
            throw new Error('State context missing event type');
        }

        console.log('Handling event in idle:', {
            type: eventType,
            context: stateContext
        });

        switch (eventType) {
            case 'NOTE_CONTENT_CLICKED': {
                const noteId = stateContext.getNoteId();
                if (!noteId) {
                    throw new Error('Note click missing note ID');
                }

                // Get current content
                const noteElement = DOMUtils.getNoteById(noteId);
                if (!noteElement) {
                    throw new Error(`Could not find note element with ID: ${noteId}`);
                }
                const content = DOMUtils.getNoteContent(noteElement);

                // Request transition to editing
                return stateContext
                    .setType('START_EDITING')
                    .setNoteId(noteId)
                    .setLastSavedContent(content)
                    .setCoordinates(stateContext.coordinates);
            }

            case 'SEARCH_FOCUSED': {
                // Request transition to searching
                return stateContext.setType('START_SEARCHING');
            }

            case 'ADD_BUTTON_CLICKED': {
                // Create new note
                const noteId = await NotesAPI.createNote();
                
                // Request transition to editing new note
                return stateContext
                    .setType('START_EDITING')
                    .setNoteId(noteId)
                    .setLastSavedContent('');
            }

            default:
                console.log('Ignoring event in idle:', eventType);
                return stateContext;
        }
    }
}; 