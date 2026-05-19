export async function exitEditingBeforeTodoToggle(options) {
    if (options === null || typeof options !== 'object') {
        throw new Error('exitEditingBeforeTodoToggle requires options object');
    }
    const { modeContext, noteId, saveAndExitEditingFn, logDebugFn } = options;
    if (!modeContext || typeof modeContext !== 'object') {
        throw new Error('exitEditingBeforeTodoToggle requires modeContext');
    }
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('exitEditingBeforeTodoToggle requires noteId');
    }
    if (typeof saveAndExitEditingFn !== 'function') {
        throw new Error('exitEditingBeforeTodoToggle requires saveAndExitEditingFn');
    }
    if (typeof logDebugFn !== 'function') {
        throw new Error('exitEditingBeforeTodoToggle requires logDebugFn');
    }

    if (!modeContext.isEditing) {
        return;
    }

    const editingNoteId = modeContext.currentNoteId;
    if (typeof editingNoteId !== 'string' || editingNoteId.length === 0) {
        throw new Error('Invariant violation: isEditing is true but currentNoteId is missing');
    }

    logDebugFn('Todo toggle clicked while editing; exiting edit mode first', {
        editingNoteId,
        targetNoteId: noteId,
    });

    await saveAndExitEditingFn();
}
