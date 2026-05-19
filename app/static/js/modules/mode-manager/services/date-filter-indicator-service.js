import { ModeContextInstance as ModeContext } from '../mode-context.js';
import { setTabDateFilterOnServer } from './tab-state-service.js';
import { getDateFilterLabel, normalizeDateFilter } from './date-filter-service.js';

let initialized = false;

export function initializeDateFilterIndicator() {
    if (initialized) {
        return;
    }
    initialized = true;
    const clearButton = document.getElementById('date-filter-indicator-clear');
    if (!(clearButton instanceof HTMLElement)) {
        throw new Error('date-filter-indicator-clear element missing');
    }
    clearButton.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        void setActiveDateFilter(null);
    });
    updateDateFilterIndicator();
}

export function updateDateFilterIndicator() {
    const indicator = document.getElementById('date-filter-indicator');
    const label = document.getElementById('date-filter-indicator-label');
    if (!(indicator instanceof HTMLElement)) {
        throw new Error('date-filter-indicator element missing');
    }
    if (!(label instanceof HTMLElement)) {
        throw new Error('date-filter-indicator-label element missing');
    }

    const dateFilter = ModeContext.activeTabDateFilter;
    if (dateFilter === null) {
        label.textContent = '';
        indicator.hidden = true;
        return;
    }

    label.textContent = getDateFilterLabel(dateFilter);
    indicator.hidden = false;
}

export async function setActiveDateFilter(dateFilter) {
    await applyActiveDateFilter(dateFilter, {
        dispatchChangeEvent: true,
        resetWindowScroll: true,
    });
}

export async function clearActiveDateFilterForSearchInput() {
    if (ModeContext.activeTabDateFilter === null) {
        return;
    }
    await applyActiveDateFilter(null, {
        dispatchChangeEvent: false,
        resetWindowScroll: false,
    });
}

async function applyActiveDateFilter(dateFilter, options) {
    if (!options || typeof options !== 'object') {
        throw new Error('applyActiveDateFilter requires options object');
    }
    const dispatchChangeEvent = options.dispatchChangeEvent === true;
    const resetWindowScroll = options.resetWindowScroll === true;
    const normalized = normalizeDateFilter(dateFilter);
    const activeTabId = ModeContext.activeTabId;
    if (typeof activeTabId !== 'string' || activeTabId.length === 0) {
        throw new Error('ModeContext.activeTabId must be a non-empty string');
    }

    const current = ModeContext.activeTabDateFilter;
    if (JSON.stringify(current) === JSON.stringify(normalized)) {
        return;
    }

    ModeContext.bumpUndoContextEpoch('dateFilter');
    const response = await setTabDateFilterOnServer(activeTabId, normalized);
    ModeContext.hydrateTabState(response, { emitUpdate: false });
    ModeContext.clearTabRevealedRedactions(activeTabId);
    ModeContext.resetTabDiffCache(activeTabId, { preserveRootAnchor: false });
    if (ModeContext.getTabScrollPosition(activeTabId) !== 0) {
        ModeContext.updateTabScroll(activeTabId, 0, false);
    }
    if (ModeContext.getTabScrollAnchor(activeTabId) !== null) {
        ModeContext.updateTabScrollAnchor(activeTabId, null, false);
    }
    if (ModeContext.getRootAnchorId() !== null) {
        ModeContext.setRootAnchorId(null);
    }
    updateDateFilterIndicator();
    if (resetWindowScroll) {
        window.scrollTo(0, 0);
    }
    if (dispatchChangeEvent) {
        window.dispatchEvent(new CustomEvent('metalist:date-filter-changed'));
    }
}
