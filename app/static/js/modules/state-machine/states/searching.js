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
    enter: async (data, prevState) => {
        // Focus search input
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.focus();
        }

        return {};
    },

    exit: async (data, nextState) => {
        return {};
    },

    handleEvent: async (event) => {
        const { type } = event;

        if (type === 'KEY_DOWN') {
            const { key } = event;

            if (key === 'Escape') {
                return { type: 'START_IDLE' };
            }

            // All other keys update search input directly
            return { type: 'NO_OP' };
        }

        if (type === 'NOTE_CONTENT_CLICKED') {
            const noteId = event.noteId;
            if (!noteId) {
                throw new Error('Note click missing noteId');
            }

            return {
                type: 'START_EDITING',
                data: {
                    noteId,
                    cursorPosition: event.position
                }
            };
        }

        throw new Error(`Unhandled event type: ${type}`);
    }
}; 