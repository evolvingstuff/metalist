import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';
import { DOMUtils } from '../../dom-utils.js';
import { StateMachine } from '../state-machine-controller.js';
import { CreateNoteEffect } from '../effects.js';

export const idleTransitions = {
    enter: async () => {
                                
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        StateMachine.currentStateContext
            .resetNoteId()
            .resetTargetNoteId()
            .resetLastSavedContent()
            .resetCursorOffset()
            .resetCoordinates()
            .resetActivityMonitor();
    },

    exit: async () => {
                                
    },

    handleEvent: async () => {
                                
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

                StateMachine.currentStateContext
                    .setTargetState('editing');
                break;
            }

            case 'SEARCH_FOCUSED': {
                                                                
                StateMachine.currentStateContext
                    .setTargetState('searching');
                break;
            }

            case 'ADD_BUTTON_CLICKED': {
                                                                
                StateMachine.currentStateContext
                    .addEffect(new CreateNoteEffect())
                    .setTargetState('editing');
                break;
            }

            case 'SEARCH_CLICKED': {
                                                                
                StateMachine.currentStateContext
                    .setTargetState('searching');
                break;
            }

            case 'KEY_DOWN': {
                                                                
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
                                                                                
                    StateMachine.currentStateContext
                        .setTargetState('searching');
                    break;
                }
                if (key === 'Enter' || (metaKey && key === 'Enter')) {
                                                                                
                    StateMachine.currentStateContext
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