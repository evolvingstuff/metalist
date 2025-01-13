import { StateContext } from '../state-context.js';
import { DOMUtils } from '../../dom-utils.js';

/**
 * Searching State
 * 
 * Manages search functionality including:
 * - Search input focus
 * - Results filtering
 * 
 * State Data:
 * 
 * Transitions:
 * - Enter: Sets up search input
 * - Exit: 
 * 
 * @example
 * // Enter search state
 * await transition('searching');
 */

export const searchingTransitions = {
    enter: async (context) => {
        // Focus search input
        const searchInput = document.querySelector('.search-input');
        if (!searchInput) {
            throw new Error('Search input not found');
        }
        searchInput.focus();

        // Clear any previous context
        return null;
    },

    exit: async () => {
        // Clear search input
        const searchInput = document.querySelector('.search-input');
        if (searchInput) {
            searchInput.value = '';
        }
    },

    handleEvent: async (stateMachineEvent) => {
        if (!stateMachineEvent) {
            throw new Error('Searching state received null/undefined event');
        }

        const { type, context } = stateMachineEvent;
        if (!type) {
            throw new Error('Event missing type');
        }

        if (type === 'KEY_DOWN') {
            const { key } = stateMachineEvent;
            if (!key) {
                throw new Error('KEY_DOWN missing key');
            }

            // Escape to exit search
            if (key === 'Escape') {
                return { type: 'START_IDLE' };
            }

            // Enter to edit selected note
            if (key === 'Enter') {
                const selectedNote = document.querySelector('.search-result.selected');
                if (!selectedNote) {
                    return context;  // No selection, stay in search
                }

                const noteId = selectedNote.dataset.noteId;
                if (!noteId) {
                    throw new Error('Selected note missing ID');
                }

                return {
                    type: 'START_EDITING',
                    context: StateContext.fromStateData({
                        noteId,
                        cursorOffset: 0,  // Start at beginning of note
                    })
                };
            }

            // Arrow keys to navigate results
            if (key.startsWith('Arrow')) {
                return context;  // Let DOM handle selection
            }

            return context;  // Regular typing handled by input
        }

        if (type === 'NOTE_CONTENT_CLICKED') {
            return {
                type: 'START_EDITING',
                context: stateMachineEvent.context  // Already validated
            };
        }

        if (type === 'CLICKED_OUTSIDE_NOTE') {
            const target = stateMachineEvent.target;
            if (!target) {
                throw new Error('Click event missing target');
            }

            // Stay in search if clicking search area
            if (target.closest('.search-container')) {
                return context;
            }

            return { type: 'START_IDLE' };
        }

        // These events don't affect search state
        if (type === 'FRAGMENT_LOADED' || 
            type === 'NO_OP') {
            return context;
        }

        throw new Error(`Unknown event type: ${type}`);
    }
};