import assert from 'node:assert/strict';
import test from 'node:test';

import { exitEditingBeforeTodoToggle } from '../../app/static/js/modules/mode-manager/services/todo-toggle-editing-service.js';

test('todo toggle exits current editing note without selecting target note', async () => {
    const calls = [];
    const modeContext = {
        isEditing: true,
        currentNoteId: 'note-a',
    };

    await exitEditingBeforeTodoToggle({
        modeContext,
        noteId: 'note-b',
        saveAndExitEditingFn: async () => {
            calls.push(['saveAndExit']);
            modeContext.isEditing = false;
            modeContext.currentNoteId = null;
        },
        logDebugFn: (message, details) => {
            calls.push(['logDebug', message, details]);
        },
    });

    assert.deepEqual(calls, [
        [
            'logDebug',
            'Todo toggle clicked while editing; exiting edit mode first',
            { editingNoteId: 'note-a', targetNoteId: 'note-b' },
        ],
        ['saveAndExit'],
    ]);
    assert.equal(modeContext.isEditing, false);
    assert.equal(modeContext.currentNoteId, null);
});

test('todo toggle does nothing before toggle when already outside edit mode', async () => {
    const calls = [];

    await exitEditingBeforeTodoToggle({
        modeContext: {
            isEditing: false,
            currentNoteId: null,
        },
        noteId: 'note-b',
        saveAndExitEditingFn: async () => {
            calls.push('saveAndExit');
        },
        logDebugFn: () => {
            calls.push('logDebug');
        },
    });

    assert.deepEqual(calls, []);
});
