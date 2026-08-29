import { ModeContextInstance as ModeContext } from '../mode-context.js';

const referenceNavigationStack = [];

function pruneReferenceNavigationStackToExistingTabs() {
    const tabOrder = ModeContext.tabOrder;
    if (!Array.isArray(tabOrder)) {
        throw new Error('ModeContext.tabOrder must be an array');
    }
    const existingTabIds = new Set(tabOrder);
    let writeIndex = 0;
    for (let i = 0; i < referenceNavigationStack.length; i += 1) {
        const entry = referenceNavigationStack[i];
        if (!entry || typeof entry !== 'object') {
            throw new Error('Reference navigation stack entry must be an object');
        }
        if (typeof entry.fromTabId !== 'string' || entry.fromTabId.length === 0) {
            throw new Error('Reference navigation stack entry missing fromTabId');
        }
        if (typeof entry.toTabId !== 'string' || entry.toTabId.length === 0) {
            throw new Error('Reference navigation stack entry missing toTabId');
        }
        if (!existingTabIds.has(entry.fromTabId) || !existingTabIds.has(entry.toTabId)) {
            continue;
        }
        referenceNavigationStack[writeIndex] = entry;
        writeIndex += 1;
    }
    referenceNavigationStack.length = writeIndex;
}

function findReferenceNavigationEntryIndexForActiveTab() {
    const activeTabId = ModeContext.activeTabId;
    for (let i = referenceNavigationStack.length - 1; i >= 0; i -= 1) {
        if (referenceNavigationStack[i].toTabId === activeTabId) {
            return i;
        }
    }
    return -1;
}

export function isViewingReferenceSource() {
    pruneReferenceNavigationStackToExistingTabs();
    return findReferenceNavigationEntryIndexForActiveTab() !== -1;
}

export function getActiveReferenceSourceQuery() {
    pruneReferenceNavigationStackToExistingTabs();
    const entryIndex = findReferenceNavigationEntryIndexForActiveTab();
    if (entryIndex === -1) {
        return '';
    }
    const entry = referenceNavigationStack[entryIndex];
    if (typeof entry.referenceQuery !== 'string' || entry.referenceQuery.length === 0) {
        throw new Error('Reference navigation entry missing referenceQuery');
    }
    return entry.referenceQuery;
}

export function updateReferenceSourceIndicator() {
    const indicator = document.getElementById('reference-source-indicator');
    if (!(indicator instanceof HTMLElement)) {
        throw new Error('reference-source-indicator element missing');
    }
    indicator.hidden = !isViewingReferenceSource();
}

export function pushReferenceNavigationEntry(fromTabId, toTabId, referenceQuery) {
    if (typeof fromTabId !== 'string' || fromTabId.length === 0) {
        throw new Error('pushReferenceNavigationEntry requires fromTabId');
    }
    if (typeof toTabId !== 'string' || toTabId.length === 0) {
        throw new Error('pushReferenceNavigationEntry requires toTabId');
    }
    if (typeof referenceQuery !== 'string' || referenceQuery.length === 0) {
        throw new Error('pushReferenceNavigationEntry requires referenceQuery');
    }
    referenceNavigationStack.push({ fromTabId, toTabId, referenceQuery });
    updateReferenceSourceIndicator();
}

export function popReferenceNavigationEntryForActiveTab() {
    pruneReferenceNavigationStackToExistingTabs();
    const entryIndex = findReferenceNavigationEntryIndexForActiveTab();
    if (entryIndex === -1) {
        updateReferenceSourceIndicator();
        return null;
    }
    const [entry] = referenceNavigationStack.splice(entryIndex, 1);
    if (!entry || typeof entry !== 'object') {
        throw new Error('Reference navigation stack entry must be an object');
    }
    updateReferenceSourceIndicator();
    return entry;
}

export function dismissReferenceSourceModeForActiveTab() {
    return popReferenceNavigationEntryForActiveTab() !== null;
}
