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