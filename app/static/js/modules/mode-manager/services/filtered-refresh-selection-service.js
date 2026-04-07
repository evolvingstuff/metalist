export function clearEditingStateForHiddenFilteredNote({
    modeContext,
    detachEditorSurfaceFn,
    clearTagBarFn,
}) {
    if (modeContext === null || typeof modeContext !== 'object') {
        throw new Error('clearEditingStateForHiddenFilteredNote requires modeContext object');
    }
    if (typeof detachEditorSurfaceFn !== 'function') {
        throw new Error('clearEditingStateForHiddenFilteredNote requires detachEditorSurfaceFn');
    }
    if (typeof clearTagBarFn !== 'function') {
        throw new Error('clearEditingStateForHiddenFilteredNote requires clearTagBarFn');
    }
    if (typeof modeContext.setCurrentContent !== 'function') {
        throw new Error('modeContext.setCurrentContent must be a function');
    }
    if (typeof modeContext.setEditing !== 'function') {
        throw new Error('modeContext.setEditing must be a function');
    }
    if (typeof modeContext.setCurrentNoteId !== 'function') {
        throw new Error('modeContext.setCurrentNoteId must be a function');
    }

    if (modeContext.currentContent !== null) {
        modeContext.setCurrentContent(null);
    }

    detachEditorSurfaceFn();
    clearTagBarFn();

    if (modeContext.isEditing) {
        modeContext.setEditing(false);
    }
    if (modeContext.currentNoteId !== null) {
        modeContext.setCurrentNoteId(null);
    }
}
