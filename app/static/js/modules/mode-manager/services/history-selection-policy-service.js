export function resolveHistoryEditingState({
    wasEditing,
    editingNoteId,
    removesEditingTarget,
}) {
    if (typeof wasEditing !== 'boolean') {
        throw new Error('wasEditing must be a boolean');
    }
    if (typeof removesEditingTarget !== 'boolean') {
        throw new Error('removesEditingTarget must be a boolean');
    }
    if (!wasEditing) {
        if (editingNoteId !== null) {
            throw new Error('editingNoteId must be null when wasEditing is false');
        }
        return { shouldEdit: false, noteId: null };
    }
    if (typeof editingNoteId !== 'string' || editingNoteId.length === 0) {
        throw new Error('editingNoteId must be a non-empty string when wasEditing is true');
    }
    if (removesEditingTarget) {
        return { shouldEdit: false, noteId: null };
    }
    return { shouldEdit: true, noteId: editingNoteId };
}
