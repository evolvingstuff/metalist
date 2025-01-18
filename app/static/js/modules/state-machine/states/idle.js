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
            .resetTargetNoteId()
            .resetLastSavedContent()
            .resetCursorOffset()
            .resetCoordinates()
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
                // Validate we have all required data
                const targetNoteId = StateMachine.currentStateContext.getTargetNoteId();
                if (!targetNoteId) {
                    throw new Error('Note click missing note ID');
                }
                
                const noteElement = DOMUtils.getNoteById(targetNoteId);
                if (!noteElement) {
                    throw new Error('Note element not found');
                }

                const coordinates = StateMachine.currentStateContext.getCoordinates();
                if (!coordinates) {
                    throw new Error('Note click missing coordinates');
                }

                const cursorOffset = StateMachine.currentStateContext.getCursorOffset();
                if (typeof cursorOffset !== 'number') {
                    throw new Error('Note click missing cursor offset');
                }

                // Request transition to editing - let transition() handle moving targetNoteId to noteId
                StateMachine.currentStateContext
                    .setType('START_EDITING')
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
                // Queue create note effect and transition to editing
                StateMachine.currentStateContext
                    .setType('START_EDITING')
                    .addEffect(new CreateNoteEffect())
                    .setTargetState('editing');
                break;
            }

            case 'KEY_DOWN': {
                // Handle keyboard shortcuts
                const key = StateMachine.currentStateContext.getKey();
                if (!key) {
                    throw new Error('Key event missing key');
                }
                const metaKey = StateMachine.currentStateContext.getMetaKey();
                if (typeof metaKey !== 'boolean') {
                    throw new Error('Key event missing meta key state');
                }
                const shiftKey = StateMachine.currentStateContext.getShiftKey();
                if (typeof shiftKey !== 'boolean') {
                    throw new Error('Key event missing shift key state');
                }

                if (metaKey && key === 'k') {
                    // Cmd+K: Focus search
                    StateMachine.currentStateContext
                        .setType('START_SEARCHING')
                        .setTargetState('searching');
                    break;
                }
                if (metaKey && key === 'n') {
                    // Cmd+N: Create new note
                    StateMachine.currentStateContext
                        .setType('START_EDITING')
                        .addEffect(new CreateNoteEffect())
                        .setTargetState('editing');
                    break;
                }
                break;
            }

            default:
                console.log('Ignoring event in idle:', eventType);
        }
    }
}; 