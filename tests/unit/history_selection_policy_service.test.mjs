import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveHistoryEditingState } from '../../app/static/js/modules/mode-manager/services/history-selection-policy-service.js';

test('application history never enters editing from view mode', () => {
    assert.deepEqual(
        resolveHistoryEditingState({
            wasEditing: false,
            editingNoteId: null,
            removesEditingTarget: false,
        }),
        { shouldEdit: false, noteId: null },
    );
});

test('application history retains an existing editor when its note survives', () => {
    assert.deepEqual(
        resolveHistoryEditingState({
            wasEditing: true,
            editingNoteId: 'note-1',
            removesEditingTarget: false,
        }),
        { shouldEdit: true, noteId: 'note-1' },
    );
});

test('application history exits editing when its mutation removes the edited note', () => {
    assert.deepEqual(
        resolveHistoryEditingState({
            wasEditing: true,
            editingNoteId: 'note-1',
            removesEditingTarget: true,
        }),
        { shouldEdit: false, noteId: null },
    );
});
