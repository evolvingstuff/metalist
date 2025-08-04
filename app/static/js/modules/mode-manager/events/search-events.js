import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { CONFIG } from '../../config.js';
import { actionRefreshAndMaybeSelect } from '../actions/ui-actions.js';

let searchTimeoutId = null;

export function handleSearchInput(event) {
    const searchQuery = event.target.value;
    
    Logger.logDebug('Search input changed', { 
        searchQuery,
        length: searchQuery.length 
    }, Logger.LogCategory.EVENT);
    
    // Update context immediately for UI responsiveness
    ModeContext.setSearchQuery(searchQuery);
    
    // Clear existing timeout
    if (searchTimeoutId) {
        clearTimeout(searchTimeoutId);
    }
    
    // Set new timeout for debounced search
    searchTimeoutId = setTimeout(async () => {
        Logger.logAction('executeSearch', { searchQuery });
        
        try {
            // Refresh the view with the search query
            await actionRefreshAndMaybeSelect();
        } catch (error) {
            Logger.logError('Search failed', error);
        }
    }, CONFIG.SEARCH.DEBOUNCE_MS);
}

export function initializeSearchEvents() {
    const searchInput = document.getElementById('search-input');
    
    if (searchInput) {
        // Add input event listener
        searchInput.addEventListener('input', handleSearchInput);
        
        // Restore search query from localStorage
        const savedQuery = ModeContext.restoreSearchQueryFromStorage();
        if (savedQuery) {
            // Update the search input field with the saved query
            searchInput.value = savedQuery;
            Logger.logAction('restoreSearchFromStorage', { searchQuery: savedQuery });
        }
        
        // Always trigger initial load - either with restored query or without
        Logger.logAction('initialPageLoad', { searchQuery: savedQuery || 'none' });
        
        try {
            actionRefreshAndMaybeSelect();
        } catch (error) {
            Logger.logError('Failed to execute initial page load', error);
        }
        
        Logger.logDebug('Search events initialized', { 
            restoredQuery: savedQuery 
        }, Logger.LogCategory.INIT);
    } else {
        Logger.logError('Search input element not found');
    }
}