/**
 * Searching State
 * 
 * Manages search functionality including:
 * - Search input focus
 * - Query persistence
 * - Results filtering
 * 
 * State Data:
 * - searchQuery: Current search string
 * - initialQuery: Starting search value
 * 
 * Transitions:
 * - Enter: Sets up search input, applies initial query
 * - Exit: Preserves search context for future use
 * 
 * @example
 * // Enter search state
 * await transition('searching', {
 *   initialQuery: 'search term'
 * });
 */

export const searchingTransitions = {
    enter: async (data, prevState) => {
        const { initialQuery = '' } = data;
        
        // Focus search input
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.value = initialQuery;
            searchInput.focus();
        }

        return {
            searchQuery: initialQuery
        };
    },

    exit: async (data, nextState) => {
        // Preserve search query across transitions
        return {
            searchQuery: data.searchQuery
        };
    }
}; 