const DELETE_KEYS = new Set(['Backspace', 'Delete']);


export function shouldDeleteSelectedNoteFromKeyboard(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('shouldDeleteSelectedNoteFromKeyboard requires options');
    }
    const {
        key,
        metaKey,
        ctrlKey,
        isEditing,
        currentNoteId,
    } = options;
    if (typeof key !== 'string') {
        throw new Error('delete shortcut key must be a string');
    }
    if (typeof metaKey !== 'boolean' || typeof ctrlKey !== 'boolean' || typeof isEditing !== 'boolean') {
        throw new Error('delete shortcut modifier and editing flags must be booleans');
    }
    if (!DELETE_KEYS.has(key)) {
        return false;
    }
    if (!(metaKey || ctrlKey)) {
        return false;
    }
    if (!isEditing) {
        return false;
    }
    return typeof currentNoteId === 'string' && currentNoteId.length > 0;
}
