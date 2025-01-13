import { DOMUtils } from '../../dom-utils.js';
import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';

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
    enter: async (stateContext) => {
        // NO MERCY validation
        if (!stateContext || !(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        console.log(' Starting search with context:', stateContext);
        
        // Focus search input
        const searchInput = DOMUtils.getSearchInput();
        if (!searchInput) {
            throw new Error('Could not find search input');
        }
        searchInput.focus();

        // Show results panel
        DOMUtils.showSearchResults();

        return stateContext;
    },

    exit: async (stateContext) => {
        // NO MERCY validation
        if (!stateContext || !(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        // Clear search input
        const searchInput = DOMUtils.getSearchInput();
        if (!searchInput) {
            throw new Error('Could not find search input');
        }
        searchInput.value = '';

        // Hide results panel
        DOMUtils.hideSearchResults();

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

        console.log('Handling event in searching:', {
            type: eventType,
            context: stateContext
        });

        switch (eventType) {
            case 'SEARCH_QUERY_CHANGED': {
                const query = stateContext.getQuery();
                if (query === undefined) {
                    throw new Error('Search query change missing query');
                }

                // Update results
                const results = await NotesAPI.searchNotes(query);
                DOMUtils.updateSearchResults(results);

                return stateContext;
            }

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

                // Switch to editing clicked note
                return stateContext
                    .setType('START_EDITING')
                    .setNoteId(noteId)
                    .setLastSavedContent(content);
            }

            case 'SEARCH_BLUR': {
                // Request transition to idle if not clicked on note
                const noteId = stateContext.getNoteId();
                if (!noteId) {
                    return stateContext.setType('START_IDLE');
                }
                return stateContext;
            }

            case 'CLICKED_OUTSIDE_NOTE': {
                // Stay in search if clicked in results panel
                const coordinates = stateContext.getCoordinates();
                if (!coordinates) {
                    throw new Error('Click missing coordinates');
                }
                
                if (DOMUtils.isInSearchResults(coordinates)) {
                    return stateContext;
                }
                
                // Otherwise go to idle
                return stateContext.setType('START_IDLE');
            }

            default:
                console.log('Ignoring event in searching:', eventType);
                return stateContext;
        }
    }
};