export function shouldActivateCommandPaletteRowClick({ row, selection }) {
    if (!row || typeof row.contains !== 'function') {
        throw new Error('shouldActivateCommandPaletteRowClick requires row with contains');
    }
    if (selection === null) {
        return true;
    }
    if (!selection || typeof selection.toString !== 'function') {
        throw new Error('shouldActivateCommandPaletteRowClick selection must expose toString');
    }

    const selectedText = selection.toString();
    if (typeof selectedText !== 'string') {
        throw new Error('Selection toString must return string');
    }
    if (selectedText.trim() === '') {
        return true;
    }

    const anchorNode = selection.anchorNode === undefined ? null : selection.anchorNode;
    const focusNode = selection.focusNode === undefined ? null : selection.focusNode;
    const selectionTouchesRow = (
        (anchorNode !== null && row.contains(anchorNode))
        || (focusNode !== null && row.contains(focusNode))
    );
    return !selectionTouchesRow;
}
