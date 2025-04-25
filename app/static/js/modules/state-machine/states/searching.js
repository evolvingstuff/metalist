import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';
import { DOMUtils } from '../../dom-utils.js';
import { StateMachine } from '../state-machine-controller.js';

export const searchingTransitions = {
    enter: async () => {
                                
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        console.log(' Starting search with context:', StateMachine.currentStateContext);

        DOMUtils.focusSearch();
    },

    exit: async () => {
                                
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }
    },

    handleEvent: async () => {
                                
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        const eventType = StateMachine.currentStateContext.getType();
        if (!eventType) {
            throw new Error('State context missing event type');
        }

        console.log('Handling event in searching:', {
            type: eventType,
            context: StateMachine.currentStateContext
        });

        switch (eventType) {
            case 'SEARCH_QUERY_CHANGED': {
                const query = StateMachine.currentStateContext.getQuery();
                if (typeof query !== 'string') {
                    throw new Error('Search query must be string');
                }

                const results = await NotesAPI.searchNotes(query);
                DOMUtils.updateSearchResults(results);
                break;
            }

            case 'SEARCH_BLURRED': {
                                                                
                const noteId = StateMachine.currentStateContext.getNoteId();
                if (!noteId) {
                    StateMachine.currentStateContext.setType('RETURN_TO_IDLE');
                }
                break;
            }

            case 'NOTE_CONTENT_CLICKED': {
                                                                
                const targetNoteId = StateMachine.currentStateContext.getTargetNoteId();
                if (!targetNoteId) {
                    throw new Error('Note click missing note ID');
                }
                                                                
                const noteElement = DOMUtils.getNoteById(targetNoteId);
                if (!noteElement) {
                    throw new Error('Note element not found');
                }

                StateMachine.currentStateContext
                    .setLastSavedContent(DOMUtils.getNoteContentHTML(noteElement))
                    .setTargetState('editing');
                break;
            }

            case 'SEARCH_CLICKED': {
                                                                
                DOMUtils.focusSearch();
                break;
            }

            case 'CLICKED_OUTSIDE_NOTE': {
                                                                
                StateMachine.currentStateContext
                    .setTargetState('idle');
                break;
            }

            default:
                throw new Error(`Unhandled event in searching state: ${eventType}`);
        }
    }
};