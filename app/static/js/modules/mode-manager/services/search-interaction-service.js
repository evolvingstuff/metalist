import { NotesAPI } from '../../api-client.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';

const SCROLL_INTERACTION_THRESHOLD_PX = 48;

const stateByTabId = Object.create(null);

function getActiveState() {
    const tabId = ModeContext.activeTabId;
    if (typeof tabId !== 'string' || tabId.length === 0) {
        throw new Error('ModeContext.activeTabId must be a non-empty string');
    }
    const state = Object.prototype.hasOwnProperty.call(stateByTabId, tabId)
        ? stateByTabId[tabId]
        : null;
    return {
        tabId,
        state,
    };
}

function getExecutedQueryForActiveTab() {
    const query = ModeContext.getExecutedSearchQuery();
    if (typeof query !== 'string') {
        throw new Error('ModeContext.getExecutedSearchQuery() must return a string');
    }
    return query;
}

function getCurrentScrollY() {
    return Math.max(0, Math.round(window.scrollY));
}

function beginPendingInteraction({ requireScrollThreshold }) {
    if (typeof requireScrollThreshold !== 'boolean') {
        throw new Error('beginPendingInteraction requires boolean requireScrollThreshold');
    }

    const { tabId, state } = getActiveState();
    if (!state) {
        return null;
    }

    const executedQuery = getExecutedQueryForActiveTab();
    if (state.query !== executedQuery) {
        return null;
    }
    if (state.pending === true || state.recorded === true) {
        return null;
    }
    if (state.hasSearchResults !== true) {
        return null;
    }
    if (executedQuery.trim() === '') {
        return null;
    }
    if (requireScrollThreshold) {
        const currentScrollY = getCurrentScrollY();
        if (Math.abs(currentScrollY - state.baselineScrollY) < SCROLL_INTERACTION_THRESHOLD_PX) {
            return null;
        }
    }

    state.pending = true;
    stateByTabId[tabId] = state;
    return executedQuery;
}

export function primeActiveSearchInteractionState() {
    const tabId = ModeContext.activeTabId;
    if (typeof tabId !== 'string' || tabId.length === 0) {
        throw new Error('ModeContext.activeTabId must be a non-empty string');
    }

    const query = getExecutedQueryForActiveTab();
    const previous = Object.prototype.hasOwnProperty.call(stateByTabId, tabId)
        ? stateByTabId[tabId]
        : null;
    const sameQuery = previous !== null && previous.query === query;
    const searchRootCountTotal = ModeContext.searchRootCountTotal;
    if (!Number.isInteger(searchRootCountTotal) || searchRootCountTotal < 0) {
        throw new Error('ModeContext.searchRootCountTotal must be a non-negative integer');
    }

    stateByTabId[tabId] = {
        query,
        baselineScrollY: getCurrentScrollY(),
        hasSearchResults: query.trim() !== '' && searchRootCountTotal > 0,
        pending: false,
        recorded: sameQuery ? previous.recorded === true : false,
    };
}

export function beginEditInteractionForActiveQuery() {
    return beginPendingInteraction({ requireScrollThreshold: false });
}

export function finalizeRecordedInteraction(query) {
    if (typeof query !== 'string' || query.length === 0) {
        throw new Error('finalizeRecordedInteraction requires query string');
    }
    const { tabId, state } = getActiveState();
    if (!state || state.query !== query) {
        return;
    }
    state.pending = false;
    state.recorded = true;
    stateByTabId[tabId] = state;
}

export function cancelPendingInteraction(query) {
    if (typeof query !== 'string' || query.length === 0) {
        throw new Error('cancelPendingInteraction requires query string');
    }
    const { tabId, state } = getActiveState();
    if (!state || state.query !== query) {
        return;
    }
    state.pending = false;
    stateByTabId[tabId] = state;
}

export async function recordScrollInteractionIfEligible() {
    const query = beginPendingInteraction({ requireScrollThreshold: true });
    if (query === null) {
        return false;
    }
    return NotesAPI.recordSearchInteraction(query, 'scroll').then(
        () => {
            finalizeRecordedInteraction(query);
            return true;
        },
        (error) => {
            cancelPendingInteraction(query);
            throw error;
        }
    );
}

export async function recordCommandInteractionIfEligible() {
    const query = beginPendingInteraction({ requireScrollThreshold: false });
    if (query === null) {
        return false;
    }
    return NotesAPI.recordSearchInteraction(query, 'command').then(
        () => {
            finalizeRecordedInteraction(query);
            return true;
        },
        (error) => {
            cancelPendingInteraction(query);
            throw error;
        }
    );
}
