export function shouldUseApplicationHistory({ isEditing }) {
    if (typeof isEditing !== 'boolean') {
        throw new Error('isEditing must be a boolean');
    }
    return !isEditing;
}

export function shouldExecuteEditorRedo({ isEditing, key }) {
    if (typeof isEditing !== 'boolean') {
        throw new Error('isEditing must be a boolean');
    }
    if (typeof key !== 'string' || key.length === 0) {
        throw new Error('key must be a non-empty string');
    }
    return isEditing && key === 'y';
}

export function executeEditorRedo(documentObject) {
    if (!documentObject || typeof documentObject.execCommand !== 'function') {
        throw new Error('Editor redo requires document.execCommand');
    }
    return documentObject.execCommand('redo');
}
