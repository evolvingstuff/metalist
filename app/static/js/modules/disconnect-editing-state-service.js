export function clearEditingStateForDisconnect(modeContext) {
    if (!modeContext || typeof modeContext !== 'object') {
        throw new Error('clearEditingStateForDisconnect requires modeContext');
    }
    if (typeof modeContext.isEditing !== 'boolean') {
        throw new Error('modeContext.isEditing must be boolean');
    }
    if (!modeContext.isEditing) {
        return false;
    }
    if (modeContext.currentNoteId === null) {
        throw new Error('Editing mode requires currentNoteId during disconnect cleanup');
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
    if (modeContext.currentContent !== null) {
        modeContext.setCurrentContent(null);
    }
    return true;
}
