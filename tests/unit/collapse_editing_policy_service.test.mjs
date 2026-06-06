import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldExitEditingBeforeCollapseToggle } from '../../app/static/js/modules/mode-manager/services/collapse-editing-policy-service.js';

test('same-note collapse toggle stays in edit mode', () => {
    assert.equal(
        shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: 'note-a',
            targetNoteId: 'note-a',
            isTargetInsideCurrentEditSubtree: true,
        }),
        false,
    );
});

test('descendant collapse toggle stays in current edit mode', () => {
    assert.equal(
        shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: 'note-a',
            targetNoteId: 'note-a-child',
            isTargetInsideCurrentEditSubtree: true,
        }),
        false,
    );
});

test('outside-note collapse toggle exits current edit mode first', () => {
    assert.equal(
        shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: 'note-a',
            targetNoteId: 'note-b',
            isTargetInsideCurrentEditSubtree: false,
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
            isTargetInsideCurrentEditSubtree: false,
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
            isTargetInsideCurrentEditSubtree: true,
        }),
        /currentNoteId/,
    );
});

test('editing collapse toggle requires subtree containment decision', () => {
    assert.throws(
        () => shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: 'note-a',
            targetNoteId: 'note-b',
        }),
        /isTargetInsideCurrentEditSubtree/,
    );
});
