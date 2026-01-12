import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { CONFIG } from '../../config.js';
import { actionRefreshAndMaybeSelect } from '../actions/ui-actions.js';
import { updateSearchContextsList } from './keyboard-events.js';
import { initializeTabStateService } from '../services/tab-state-service.js';
import { analyzeSearchQueryInput } from '../services/search-syntax-service.js';
import { enforceSearchInputElement, setSearchValidationState, syncSearchInputValue } from '../services/search-input-service.js';

let searchTimeoutId = null;

export function handleSearchInput(event) {
    if (ModeContext.isLoading) {
        let currentValue = '';
        if (event && event.target && typeof event.target.value === 'string') {
            currentValue = event.target.value;
        }

        Logger.logNoop('Search input ignored while request in-flight', {
            value: currentValue,
            activeTab: ModeContext.activeTabId,
        });
        event.preventDefault();
        return;
    }

    const searchInput = event.target;
    if (!searchInput || typeof searchInput.value !== 'string') {
        throw new Error('Search input handler requires event.target input element');
    }

    const enforcedValue = enforceSearchInputElement(searchInput);
    const analysis = analyzeSearchQueryInput(enforcedValue);
    setSearchValidationState(searchInput, analysis);

    Logger.logDebug('Search input changed', {
        searchQuery: analysis.normalizedText,
        length: analysis.normalizedText.length,
        isComplete: analysis.isComplete,
    }, Logger.LogCategory.EVENT);

    // Update context immediately for UI responsiveness
    ModeContext.setSearchQuery(analysis.normalizedText);

    // Update search contexts list display
    updateSearchContextsList();

    // Clear existing timeout
    if (searchTimeoutId) {
        clearTimeout(searchTimeoutId);
    }

    // Set new timeout for debounced search
    searchTimeoutId = setTimeout(async () => {
        const currentSearch = ModeContext.searchQuery;
        const currentAnalysis = analyzeSearchQueryInput(currentSearch);

        if (!currentAnalysis.isComplete) {
            Logger.logNoop('Search execution skipped: incomplete query', {
                searchQuery: currentSearch,
                warningMessage: currentAnalysis.warningMessage,
            });
            return;
        }

        Logger.logAction('executeSearch', { searchQuery: currentSearch });
        ModeContext.clearActiveTabDiffCacheForSearchExecution(currentSearch);
        ModeContext.resetRootTracking({ clear: true });
        window.scrollTo(0, 0);
        ModeContext.updateActiveTabScroll(0);
        ModeContext.updateActiveTabScrollAnchor(null, true);
        ModeContext.setRootAnchorId(null);
        // Refresh the view with the search query (let errors crash)
        await actionRefreshAndMaybeSelect({});
    }, CONFIG.SEARCH.DEBOUNCE_MS);
}

export async function initializeSearchEvents() {
    const startedAt = performance.now();
    const searchInput = document.getElementById('search-input');

    if (!searchInput || typeof searchInput.addEventListener !== 'function') {
        Logger.logError('Search input element not found');
        return;
    }

    // Add input event listener
    searchInput.addEventListener('input', handleSearchInput);

    await initializeTabStateService();

    const activeTabQuery = ModeContext.searchQuery;
    if (typeof activeTabQuery !== 'string') {
        throw new Error('ModeContext.searchQuery must be a string');
    }

    // Update tab indicator on page load
    const tabIndicator = document.getElementById('tab-indicator');
    if (tabIndicator) {
        tabIndicator.textContent = ModeContext.activeTabId;
    }

    // Initialize search contexts list
    updateSearchContextsList();

    // Always sync the input field to the active tab query.
    const analysis = syncSearchInputValue(searchInput, activeTabQuery);
    ModeContext.setSearchQuery(analysis.normalizedText);

    const initialQueryLogValue = analysis.normalizedText.length > 0 ? analysis.normalizedText : 'none';
    Logger.logAction('initialPageLoad', { searchQuery: initialQueryLogValue });

    ModeContext.setExecutedSearchQuery(analysis.normalizedText);
    await actionRefreshAndMaybeSelect({ startedAt: startedAt, context: 'init search' });
    ModeContext.restoreScrollForActiveTab();

    Logger.logDebug('Search events initialized', {
        activeTab: ModeContext.activeTabId,
        restoredQuery: analysis.normalizedText,
    }, Logger.LogCategory.INIT);
}
