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
        
        // Initialize with any existing value
        if (searchInput.value) {
            ModeContext.setSearchQuery(searchInput.value);
        }
        
        Logger.logDebug('Search events initialized', {}, Logger.LogCategory.INIT);
    } else {
        Logger.logError('Search input element not found');
    }
}