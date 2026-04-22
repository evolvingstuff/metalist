import assert from 'node:assert/strict';
import test from 'node:test';

import { prepareMoveNoteToTopContextAction } from '../../app/static/js/modules/mode-manager/services/note-context-menu-action-service.js';

test('prepareMoveNoteToTopContextAction saves the currently edited different note and keeps target unselected', async () => {
    const saved = [];
    let exitSearchCalls = 0;

    await prepareMoveNoteToTopContextAction({
        targetNoteId: 'note-b',
        modeContext: {
            isSearching: false,
            isEditing: true,
            currentNoteId: 'note-a',
            editSessionHasEdits: true,
        },
        exitSearchModeFn() {
            exitSearchCalls += 1;
        },
        saveActiveNoteFn(noteId) {
            saved.push(noteId);
            return Promise.resolve();
        },
    });

    assert.equal(exitSearchCalls, 0);
    assert.deepEqual(saved, ['note-a']);
});

test('prepareMoveNoteToTopContextAction does not save when target note is already selected', async () => {
    const saved = [];
    let exitSearchCalls = 0;

    await prepareMoveNoteToTopContextAction({
        targetNoteId: 'note-a',
        modeContext: {
            isSearching: true,
            isEditing: true,
            currentNoteId: 'note-a',
            editSessionHasEdits: true,
        },
        exitSearchModeFn() {
            exitSearchCalls += 1;
        },
        saveActiveNoteFn(noteId) {
            saved.push(noteId);
            return Promise.resolve();
        },
    });

    assert.equal(exitSearchCalls, 1);
    assert.deepEqual(saved, []);
});

test('prepareMoveNoteToTopContextAction is a no-op for non-editing state', async () => {
    const saved = [];
    let exitSearchCalls = 0;

    await prepareMoveNoteToTopContextAction({
        targetNoteId: 'note-b',
        modeContext: {
            isSearching: false,
            isEditing: false,
            currentNoteId: null,
            editSessionHasEdits: false,
        },
        exitSearchModeFn() {
            exitSearchCalls += 1;
        },
        saveActiveNoteFn(noteId) {
            saved.push(noteId);
            return Promise.resolve();
        },
    });

    assert.equal(exitSearchCalls, 0);
    assert.deepEqual(saved, []);
});
