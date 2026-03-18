const NOTE_CLIPBOARD_HTML_MARKER = 'class="note-content"';

function assertClipboardMode(clipboardMode) {
    if (clipboardMode !== 'system' && clipboardMode !== 'note') {
        throw new Error(`Invalid clipboard mode: ${clipboardMode}`);
    }
}

export function clipboardHtmlContainsNoteContent(clipboardHtml) {
    if (typeof clipboardHtml !== 'string') {
        throw new Error('clipboardHtml must be a string');
    }
    return clipboardHtml.includes(NOTE_CLIPBOARD_HTML_MARKER);
}

export function shouldAllowBrowserPasteForShortcut({
    clipboardMode,
    noteClipboardRequiresBrowserValidation,
    isEditing,
    currentNoteId,
}) {
    assertClipboardMode(clipboardMode);
    if (typeof noteClipboardRequiresBrowserValidation !== 'boolean') {
        throw new Error('noteClipboardRequiresBrowserValidation must be a boolean');
    }
    if (typeof isEditing !== 'boolean') {
        throw new Error('isEditing must be a boolean');
    }

    const hasCurrentNoteId = typeof currentNoteId === 'string' && currentNoteId.length > 0;

    if (clipboardMode === 'system') {
        return true;
    }
    if (noteClipboardRequiresBrowserValidation) {
        return true;
    }
    if (!isEditing) {
        return true;
    }
    if (!hasCurrentNoteId) {
        return true;
    }
    return false;
}

export function resolveClipboardTrackingAfterPasteEvent({
    clipboardMode,
    noteClipboardRequiresBrowserValidation,
    clipboardHtml,
}) {
    assertClipboardMode(clipboardMode);
    if (typeof noteClipboardRequiresBrowserValidation !== 'boolean') {
        throw new Error('noteClipboardRequiresBrowserValidation must be a boolean');
    }
    if (typeof clipboardHtml !== 'string') {
        throw new Error('clipboardHtml must be a string');
    }

    const hasNoteClipboardHtml = clipboardHtmlContainsNoteContent(clipboardHtml);
    if (clipboardMode === 'note' && noteClipboardRequiresBrowserValidation) {
        if (hasNoteClipboardHtml) {
            return {
                clipboardMode: 'note',
                noteClipboardRequiresBrowserValidation: false,
                hasNoteClipboardHtml: true,
            };
        }
        return {
            clipboardMode: 'system',
            noteClipboardRequiresBrowserValidation: false,
            hasNoteClipboardHtml: false,
        };
    }

    return {
        clipboardMode,
        noteClipboardRequiresBrowserValidation,
        hasNoteClipboardHtml,
    };
}
