export function shouldExitEditingBeforeCollapseToggle({ isEditing, currentNoteId, targetNoteId }) {
    if (typeof isEditing !== 'boolean') {
        throw new Error('shouldExitEditingBeforeCollapseToggle requires boolean isEditing');
    }
    if (typeof targetNoteId !== 'string' || targetNoteId.length === 0) {
        throw new Error('shouldExitEditingBeforeCollapseToggle requires targetNoteId');
    }

    if (!isEditing) {
        return false;
    }

    if (typeof currentNoteId !== 'string' || currentNoteId.length === 0) {
        throw new Error('editing collapse toggle requires currentNoteId');
    }

    return currentNoteId !== targetNoteId;
}
