function requireBoolean(name, value) {
    if (typeof value !== 'boolean') {
        throw new Error(`${name} must be a boolean`);
    }
}

export function shouldMarkExpandedEditSession({
    isEditing,
    currentNoteId,
    targetNoteId,
    expandedPersisted,
}) {
    requireBoolean('isEditing', isEditing);
    requireBoolean('expandedPersisted', expandedPersisted);
    if (
        currentNoteId !== null
        && (typeof currentNoteId !== 'string' || currentNoteId.length === 0)
    ) {
        throw new Error('currentNoteId must be a non-empty string or null');
    }
    if (typeof targetNoteId !== 'string' || targetNoteId.length === 0) {
        throw new Error('targetNoteId must be a non-empty string');
    }
    return (
        isEditing
        && currentNoteId === targetNoteId
        && !expandedPersisted
    );
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
