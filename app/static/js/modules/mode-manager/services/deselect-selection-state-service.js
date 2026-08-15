export function clearSelectionStateForDeselect(modeContext) {
    if (modeContext === null || typeof modeContext !== 'object') {
        throw new Error('clearSelectionStateForDeselect requires modeContext object');
    }
    if (modeContext.isEditing !== true) {
        throw new Error('clearSelectionStateForDeselect requires active editing state');
    }
    if (typeof modeContext.currentNoteId !== 'string' || modeContext.currentNoteId.length === 0) {
        throw new Error('clearSelectionStateForDeselect requires currentNoteId');
    }
    if (typeof modeContext.setEditing !== 'function') {
        throw new Error('modeContext.setEditing must be a function');
    }
    if (typeof modeContext.setCurrentNoteId !== 'function') {
        throw new Error('modeContext.setCurrentNoteId must be a function');
    }
    if (typeof modeContext.setCurrentContent !== 'function') {
        throw new Error('modeContext.setCurrentContent must be a function');
    }

    modeContext.setEditing(false);
    modeContext.setCurrentNoteId(null);
    // A refresh can remove the edited note before deselection finishes, clearing its content first.
    if (modeContext.currentContent !== null) {
        modeContext.setCurrentContent(null);
    }
}
