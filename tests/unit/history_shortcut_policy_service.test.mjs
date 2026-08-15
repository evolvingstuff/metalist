import assert from 'node:assert/strict';
import test from 'node:test';

import {
    executeEditorRedo,
    shouldExecuteEditorRedo,
    shouldUseApplicationHistory,
} from '../../app/static/js/modules/mode-manager/services/history-shortcut-policy-service.js';

test('undo and redo stay native whenever a note editor is active', () => {
    assert.equal(shouldUseApplicationHistory({ isEditing: true }), false);
});

test('undo and redo use saved application history outside note editing', () => {
    assert.equal(shouldUseApplicationHistory({ isEditing: false }), true);
});

test('history shortcut policy rejects non-boolean editing state', () => {
    assert.throws(
        () => shouldUseApplicationHistory({ isEditing: null }),
        /isEditing must be a boolean/,
    );
});

test('Cmd/Ctrl+Y maps to local editor redo while editing', () => {
    assert.equal(shouldExecuteEditorRedo({ isEditing: true, key: 'y' }), true);
    assert.equal(shouldExecuteEditorRedo({ isEditing: true, key: 'z' }), false);
    assert.equal(shouldExecuteEditorRedo({ isEditing: false, key: 'y' }), false);
});

test('local editor redo invokes the active document undo manager', () => {
    const calls = [];
    const documentObject = {
        execCommand(command) {
            calls.push(command);
            return true;
        },
    };

    assert.equal(executeEditorRedo(documentObject), true);
    assert.deepEqual(calls, ['redo']);
});
