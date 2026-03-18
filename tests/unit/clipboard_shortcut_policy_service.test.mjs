import assert from 'node:assert/strict';
import test from 'node:test';

import {
    resolveClipboardTrackingAfterPasteEvent,
    shouldAllowBrowserPasteForShortcut,
} from '../../app/static/js/modules/mode-manager/services/clipboard-shortcut-policy-service.js';

test('intercepts paste shortcut when note clipboard is trusted and a note is active', () => {
    const allowBrowserPaste = shouldAllowBrowserPasteForShortcut({
        clipboardMode: 'note',
        noteClipboardRequiresBrowserValidation: false,
        isEditing: true,
        currentNoteId: 'note-123',
    });

    assert.equal(allowBrowserPaste, false);
});

test('allows browser paste when note clipboard must be revalidated after app blur', () => {
    const allowBrowserPaste = shouldAllowBrowserPasteForShortcut({
        clipboardMode: 'note',
        noteClipboardRequiresBrowserValidation: true,
        isEditing: true,
        currentNoteId: 'note-123',
    });

    assert.equal(allowBrowserPaste, true);
});

test('demotes stale note clipboard tracking when actual paste contents are external', () => {
    const resolved = resolveClipboardTrackingAfterPasteEvent({
        clipboardMode: 'note',
        noteClipboardRequiresBrowserValidation: true,
        clipboardHtml: '',
    });

    assert.deepEqual(resolved, {
        clipboardMode: 'system',
        noteClipboardRequiresBrowserValidation: false,
        hasNoteClipboardHtml: false,
    });
});

test('keeps note clipboard tracking when actual paste contents still contain a MetaList note', () => {
    const resolved = resolveClipboardTrackingAfterPasteEvent({
        clipboardMode: 'note',
        noteClipboardRequiresBrowserValidation: true,
        clipboardHtml: '<div class="note-content">Copied note</div>',
    });

    assert.deepEqual(resolved, {
        clipboardMode: 'note',
        noteClipboardRequiresBrowserValidation: false,
        hasNoteClipboardHtml: true,
    });
});
