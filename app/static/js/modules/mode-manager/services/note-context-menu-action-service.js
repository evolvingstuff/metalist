export async function prepareMoveNoteToTopContextAction(options) {
    if (options === null || typeof options !== 'object') {
        throw new Error('prepareMoveNoteToTopContextAction requires options object');
    }

    const {
        targetNoteId,
        modeContext,
        exitSearchModeFn,
        saveActiveNoteFn,
    } = options;

    if (typeof targetNoteId !== 'string' || targetNoteId.trim() === '') {
        throw new Error('prepareMoveNoteToTopContextAction requires targetNoteId');
    }
    if (modeContext === null || typeof modeContext !== 'object') {
        throw new Error('prepareMoveNoteToTopContextAction requires modeContext object');
    }
    if (typeof exitSearchModeFn !== 'function') {
        throw new Error('prepareMoveNoteToTopContextAction requires exitSearchModeFn');
    }
    if (typeof saveActiveNoteFn !== 'function') {
        throw new Error('prepareMoveNoteToTopContextAction requires saveActiveNoteFn');
    }

    if (modeContext.isSearching) {
        exitSearchModeFn();
    }

    if (!modeContext.isEditing) {
        return;
    }

    const currentNoteId = modeContext.currentNoteId;
    if (typeof currentNoteId !== 'string' || currentNoteId.length === 0) {
        throw new Error('prepareMoveNoteToTopContextAction requires currentNoteId while editing');
    }
    if (currentNoteId === targetNoteId) {
        return;
    }
    if (!modeContext.editSessionHasEdits) {
        return;
    }

    await saveActiveNoteFn(currentNoteId);
}
