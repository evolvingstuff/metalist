import assert from 'node:assert/strict';
import test from 'node:test';

import {
    shouldDeleteSelectedNoteFromKeyboard,
} from '../../app/static/js/modules/mode-manager/services/note-delete-shortcut-policy-service.js';


function shortcutOptions(overrides = {}) {
    return {
        key: 'Backspace',
        metaKey: true,
        ctrlKey: false,
        isEditing: true,
        currentNoteId: 'note-1',
        ...overrides,
    };
}


test('modified delete removes the actively selected editing note', () => {
    assert.equal(shouldDeleteSelectedNoteFromKeyboard(shortcutOptions()), true);
    assert.equal(shouldDeleteSelectedNoteFromKeyboard(shortcutOptions({ key: 'Delete' })), true);
});


test('unmodified delete never removes a hovered idle note', () => {
    assert.equal(shouldDeleteSelectedNoteFromKeyboard(shortcutOptions({
        metaKey: false,
        isEditing: false,
        currentNoteId: null,
    })), false);
});


test('modified delete requires an actively selected editing note', () => {
    assert.equal(shouldDeleteSelectedNoteFromKeyboard(shortcutOptions({ isEditing: false })), false);
    assert.equal(shouldDeleteSelectedNoteFromKeyboard(shortcutOptions({ currentNoteId: null })), false);
});
