import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';
import { DOMUtils } from '../../dom-utils.js';
import { StateMachine } from '../state-machine-controller.js';

/**
 * Searching State
 * 
 * Manages search functionality including:
 * - Search input focus
 * - Query handling
 * - Results display
 * 
 * State Context:
 * - query: Current search query
 * 
 * Transitions:
 * - Enter: Focus search input, show results panel
 * - Exit: Clear results, restore normal view
 * 
 * @example
 * // Enter searching state
 * stateContext
 *   .setType('START_SEARCHING')
 *   .setQuery('');
 */

export const searchingTransitions = {
    enter: async () => {
        // Validate context
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        console.log(' Starting search with context:', StateMachine.currentStateContext);
        
        // Focus search input
        DOMUtils.focusSearch();

        // Show results panel
        DOMUtils.showSearchResults();
    },

    exit: async () => {
        // Validate context
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        // Clear search input
        DOMUtils.clearSearch();

        // Hide results panel
        DOMUtils.hideSearchResults();
    },

    handleEvent: async () => {
        // Validate context
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

                // Update search results
                const results = await NotesAPI.searchNotes(query);
                DOMUtils.updateSearchResults(results);
                break;
            }

            case 'SEARCH_BLURRED': {
                // Return to idle if not clicking on note
                const noteId = StateMachine.currentStateContext.getNoteId();
                if (!noteId) {
                    StateMachine.currentStateContext.setType('RETURN_TO_IDLE');
                }
                break;
            }

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

                // Let transition() handle moving targetNoteId to noteId
                StateMachine.currentStateContext
                    .setLastSavedContent(DOMUtils.getNoteContentHTML(noteElement))
                    .setTargetState('editing');
                break;
            }

            case 'CLICKED_OUTSIDE_NOTE': {
                // Stay in search if clicked in results panel
                const coordinates = StateMachine.currentStateContext.getCoordinates();
                if (!coordinates) {
                    throw new Error('Click missing coordinates');
                }
                
                if (DOMUtils.isInSearchResults(coordinates)) {
                    break;
                }
                
                // Otherwise go to idle
                StateMachine.currentStateContext.setType('RETURN_TO_IDLE');
                break;
            }

            default:
                throw new Error(`Unhandled event in searching state: ${eventType}`);
        }
    }
};