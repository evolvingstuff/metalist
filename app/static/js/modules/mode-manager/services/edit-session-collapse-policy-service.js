function requireBoolean(name, value) {
    if (typeof value !== 'boolean') {
        throw new Error(`${name} must be a boolean`);
    }
}

export function shouldPersistExpandedEditSession({ startedCollapsed, hasEdits, expandedPersisted }) {
    requireBoolean('startedCollapsed', startedCollapsed);
    requireBoolean('hasEdits', hasEdits);
    requireBoolean('expandedPersisted', expandedPersisted);
    return false;
}

export function shouldRestoreCollapsedStateLocally({ startedCollapsed, hasEdits, expandedPersisted }) {
    requireBoolean('startedCollapsed', startedCollapsed);
    requireBoolean('hasEdits', hasEdits);
    requireBoolean('expandedPersisted', expandedPersisted);
    return startedCollapsed && !hasEdits && !expandedPersisted;
}
