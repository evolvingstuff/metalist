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

export async function initializeSearchEvents() {
    const searchInput = document.getElementById('search-input');
    
    if (searchInput) {
        // Add input event listener
        searchInput.addEventListener('input', handleSearchInput);
        
        // Restore tab state from localStorage (this also restores search query)
        ModeContext.restoreTabStateFromStorage();
        const activeTabQuery = ModeContext.searchQuery;
        
        if (activeTabQuery) {
            // Update the search input field with the active tab's query
            searchInput.value = activeTabQuery;
            Logger.logAction('restoreTabStateFromStorage', { 
                activeTab: ModeContext.activeTabId,
                searchQuery: activeTabQuery 
            });
        }
        
        // Always trigger initial load - either with restored query or without
        Logger.logAction('initialPageLoad', { searchQuery: activeTabQuery || 'none' });
        
        try {
            await actionRefreshAndMaybeSelect();
            
            // Restore scroll position for the active tab
            const scrollY = ModeContext.getTabScrollPosition();
            if (scrollY > 0) {
                window.scrollTo(0, scrollY);
                Logger.logDebug('Restored scroll position', { scrollY });
            }
        } catch (error) {
            Logger.logError('Failed to execute initial page load', error);
        }
        
        Logger.logDebug('Search events initialized', { 
            activeTab: ModeContext.activeTabId,
            restoredQuery: activeTabQuery 
        }, Logger.LogCategory.INIT);
    } else {
        Logger.logError('Search input element not found');
    }
}