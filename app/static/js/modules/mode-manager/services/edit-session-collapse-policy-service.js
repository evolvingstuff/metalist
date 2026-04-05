function requireBoolean(name, value) {
    if (typeof value !== 'boolean') {
        throw new Error(`${name} must be a boolean`);
    }
}

export function shouldPersistExpandedEditSession({ startedCollapsed, hasEdits, expandedPersisted }) {
    requireBoolean('startedCollapsed', startedCollapsed);
    requireBoolean('hasEdits', hasEdits);
    requireBoolean('expandedPersisted', expandedPersisted);
    return startedCollapsed && hasEdits && !expandedPersisted;
}

export function shouldRestoreCollapsedStateLocally({ startedCollapsed, hasEdits }) {
    requireBoolean('startedCollapsed', startedCollapsed);
    requireBoolean('hasEdits', hasEdits);
    return startedCollapsed && !hasEdits;
}
