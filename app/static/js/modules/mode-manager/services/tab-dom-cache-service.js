const tabDomCache = new Map();

function requireNotesContainer() {
    const notesContainer = document.getElementById('notes-container');
    if (!notesContainer) {
        throw new Error('Notes container not found');
    }
    return notesContainer;
}

function requireTabId(tabId) {
    if (typeof tabId !== 'string' || tabId.length === 0) {
        throw new Error('tabId must be a non-empty string');
    }
}

function ensureCacheContainer(tabId) {
    requireTabId(tabId);
    let container = tabDomCache.get(tabId);
    if (!container) {
        container = document.createElement('div');
        container.dataset.tabId = tabId;
        tabDomCache.set(tabId, container);
    }
    return container;
}

export function cacheNotesDomForTab(tabId) {
    requireTabId(tabId);
    const notesContainer = requireNotesContainer();
    const cacheContainer = ensureCacheContainer(tabId);

    let moved = 0;
    while (notesContainer.firstChild) {
        cacheContainer.appendChild(notesContainer.firstChild);
        moved += 1;
    }

    return { moved };
}

export function restoreNotesDomForTab(tabId) {
    requireTabId(tabId);
    const notesContainer = requireNotesContainer();
    const cacheContainer = tabDomCache.get(tabId);
    if (!cacheContainer) {
        return { restored: false, moved: 0 };
    }

    const hadNodes = cacheContainer.childNodes.length > 0;
    let moved = 0;
    while (cacheContainer.firstChild) {
        notesContainer.appendChild(cacheContainer.firstChild);
        moved += 1;
    }

    return { restored: hadNodes, moved };
}

export function clearAllCachedNotesDom() {
    tabDomCache.clear();
}
