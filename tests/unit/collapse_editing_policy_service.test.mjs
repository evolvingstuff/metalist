import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldExitEditingBeforeCollapseToggle } from '../../app/static/js/modules/mode-manager/services/collapse-editing-policy-service.js';

test('same-note collapse toggle stays in edit mode', () => {
    assert.equal(
        shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: 'note-a',
            targetNoteId: 'note-a',
        }),
        false,
    );
});

test('different-note collapse toggle exits current edit mode first', () => {
    assert.equal(
        shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: 'note-a',
            targetNoteId: 'note-b',
        }),
        true,
    );
});

test('collapse toggle outside edit mode does not exit edit mode', () => {
    assert.equal(
        shouldExitEditingBeforeCollapseToggle({
            isEditing: false,
            currentNoteId: null,
            targetNoteId: 'note-a',
        }),
        false,
    );
});

test('editing collapse toggle fails when current note is missing', () => {
    assert.throws(
        () => shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: null,
            targetNoteId: 'note-a',
        }),
        /currentNoteId/,
    );
});
