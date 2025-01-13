import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';
import { DOMUtils } from '../../dom-utils.js';
import { StateMachine } from '../state-machine-controller.js';
import { CreateNoteEffect } from '../effects.js';

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
 * StateMachine.currentStateContext.setTargetState('idle');
 * await StateMachine.transition();
 */

export const idleTransitions = {
    enter: async () => {
        // Validate context
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }
        
        // Clear all note-related state
        StateMachine.currentStateContext
            .resetNoteId()
            .resetLastSavedContent()
            .resetCursorOffset()
            .resetActivityMonitor();
    },

    exit: async () => {
        // Nothing to clean up
    },

    handleEvent: async () => {
        // NO MERCY validation
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        const eventType = StateMachine.currentStateContext.getType();
        if (!eventType) {
            throw new Error('State context missing event type');
        }

        console.log('Handling event in idle:', {
            type: eventType,
            context: StateMachine.currentStateContext
        });

        switch (eventType) {
            case 'NOTE_CONTENT_CLICKED': {
                const noteId = StateMachine.currentStateContext.getNoteId();
                if (!noteId) {
                    throw new Error('Note click missing note ID');
                }
                
                const noteElement = DOMUtils.getNoteById(noteId);
                if (!noteElement) {
                    throw new Error('Note element not found');
                }
                
                const content = DOMUtils.getNoteContent(noteElement);

                // Request transition to editing
                StateMachine.currentStateContext
                    .setType('START_EDITING')
                    .setNoteId(noteId)
                    .setLastSavedContent(content)
                    .setCoordinates(StateMachine.currentStateContext.coordinates)
                    .setTargetState('editing');
                break;
            }

            case 'SEARCH_FOCUSED': {
                // Request transition to searching
                StateMachine.currentStateContext
                    .setType('START_SEARCHING')
                    .setTargetState('searching');
                break;
            }

            case 'ADD_BUTTON_CLICKED': {
                // Create new note
                const noteId = await NotesAPI.createNote();
                
                StateMachine.currentStateContext
                    .setType('NOTE_CONTENT_CLICKED')
                    .setNoteId(noteId)
                    .setLastSavedContent('');
                break;
            }

            case 'CLICKED_OUTSIDE_NOTE': {
                // Do nothing - we're already in idle
                break;
            }

            case 'KEY_DOWN': {
                const key = StateMachine.currentStateContext.getKey();
                if (key === 'Enter') {
                    StateMachine.currentStateContext
                        .addEffect(new CreateNoteEffect())
                        .setTargetState('editing');
                }
                break;
            }

            default:
                throw new Error(`Unhandled event in idle state: ${eventType}`);
        }
    }
}; 