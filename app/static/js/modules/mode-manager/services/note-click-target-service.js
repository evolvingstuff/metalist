function supportsClosest(target) {
    return target !== null && typeof target === 'object' && typeof target.closest === 'function';
}

export function resolveNonContentNoteSelectionTarget(target) {
    if (!supportsClosest(target)) {
        return null;
    }

    if (target.closest('.note-content')) {
        return null;
    }

    if (target.closest('.note-tag-bar')) {
        return null;
    }

    return target.closest('.note');
}
