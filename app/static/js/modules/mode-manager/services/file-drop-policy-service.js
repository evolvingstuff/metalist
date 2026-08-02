export function shouldCreateTopNoteForFileDrop({
    isEditing,
    currentNoteId,
    hasNonImageFile,
    hasEditingDropTarget,
}) {
    if (typeof isEditing !== 'boolean') {
        throw new Error('File drop isEditing must be a boolean');
    }
    if (currentNoteId !== null && typeof currentNoteId !== 'string') {
        throw new Error('File drop currentNoteId must be a string or null');
    }
    if (isEditing && (typeof currentNoteId !== 'string' || currentNoteId.length === 0)) {
        throw new Error('File drop requires currentNoteId while editing');
    }
    if (!isEditing && currentNoteId !== null) {
        throw new Error('File drop cannot have currentNoteId outside editing mode');
    }
    if (typeof hasNonImageFile !== 'boolean') {
        throw new Error('File drop hasNonImageFile must be a boolean');
    }
    if (typeof hasEditingDropTarget !== 'boolean') {
        throw new Error('File drop hasEditingDropTarget must be a boolean');
    }

    if (!isEditing) {
        return true;
    }
    if (hasNonImageFile) {
        return false;
    }
    return !hasEditingDropTarget;
}
