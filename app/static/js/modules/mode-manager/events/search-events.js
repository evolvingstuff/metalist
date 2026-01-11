import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { CONFIG } from '../../config.js';
import { actionRefreshAndMaybeSelect } from '../actions/ui-actions.js';
import { updateSearchContextsList } from './keyboard-events.js';
import { initializeTabStateService } from '../services/tab-state-service.js';

let searchTimeoutId = null;

export function handleSearchInput(event) {
    if (ModeContext.isLoading) {
        Logger.logNoop('Search input ignored while request in-flight', {
            value: event?.target?.value || '',
            activeTab: ModeContext.activeTabId
        });
        event.preventDefault();
        return;
    }
    const searchQuery = event.target.value;
    
    Logger.logDebug('Search input changed', { 
        searchQuery,
        length: searchQuery.length 
    }, Logger.LogCategory.EVENT);
    
    // Update context immediately for UI responsiveness
    ModeContext.setSearchQuery(searchQuery);
    
    // Update search contexts list display
    updateSearchContextsList();
    
    // Clear existing timeout
    if (searchTimeoutId) {
        clearTimeout(searchTimeoutId);
    }
    
    // Set new timeout for debounced search
	    searchTimeoutId = setTimeout(async () => {
	        Logger.logAction('executeSearch', { searchQuery });
	        // Refresh the view with the search query (let errors crash)
	        await actionRefreshAndMaybeSelect({});
	    }, CONFIG.SEARCH.DEBOUNCE_MS);
	}

export async function initializeSearchEvents() {
    let startedAt = performance.now();
    const searchInput = document.getElementById('search-input');
    
    if (searchInput) {  //BS
        // Add input event listener
        searchInput.addEventListener('input', handleSearchInput);
        
        await initializeTabStateService();
        const activeTabQuery = ModeContext.searchQuery;
        
        // Update tab indicator on page load
        const tabIndicator = document.getElementById('tab-indicator');
        if (tabIndicator) {
            tabIndicator.textContent = ModeContext.activeTabId;
        }
        
        // Initialize search contexts list
        updateSearchContextsList();
        
        if (activeTabQuery) {
            // Update the search input field with the active tab's query
            searchInput.value = activeTabQuery;
            Logger.logAction('hydrateTabStateFromServer', {
                activeTab: ModeContext.activeTabId,
                searchQuery: activeTabQuery
            });
        }
        
        // Always trigger initial load - either with restored query or without
        Logger.logAction('initialPageLoad', { searchQuery: activeTabQuery || 'none' });
        
        await actionRefreshAndMaybeSelect({startedAt: startedAt, context: "init search"});
        ModeContext.restoreScrollForActiveTab();
        
        Logger.logDebug('Search events initialized', { 
            activeTab: ModeContext.activeTabId,
            restoredQuery: activeTabQuery 
        }, Logger.LogCategory.INIT);
    } else {
        Logger.logError('Search input element not found');
    }
}
