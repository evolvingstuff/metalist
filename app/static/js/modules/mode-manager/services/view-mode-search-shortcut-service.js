export function shouldFocusSearchInputForViewModeTab(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('shouldFocusSearchInputForViewModeTab requires options');
    }

    const {
        key,
        shiftKey,
        altKey,
        metaKey,
        ctrlKey,
        isEditing,
        isSearching,
        isLoading,
        modalStack,
    } = options;

    if (typeof key !== 'string') {
        throw new Error('shouldFocusSearchInputForViewModeTab requires key');
    }
    if (!Array.isArray(modalStack)) {
        throw new Error('shouldFocusSearchInputForViewModeTab requires modalStack array');
    }

    if (key !== 'Tab') {
        return false;
    }
    if (shiftKey || altKey || metaKey || ctrlKey) {
        return false;
    }
    if (isEditing || isSearching || isLoading) {
        return false;
    }
    return modalStack.length === 0;
}
