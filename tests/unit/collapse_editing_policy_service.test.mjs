import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldExitEditingBeforeCollapseToggle } from '../../app/static/js/modules/mode-manager/services/collapse-editing-policy-service.js';

test('collapsing the edited note exits edit mode', () => {
    assert.equal(
        shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: 'note-a',
            targetNoteId: 'note-a',
            isTargetInsideCurrentEditSubtree: true,
            collapsed: true,
        }),
        true,
    );
});

test('expanding the edited note stays in edit mode', () => {
    assert.equal(
        shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: 'note-a',
            targetNoteId: 'note-a',
            isTargetInsideCurrentEditSubtree: true,
            collapsed: false,
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
            collapsed: true,
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
            collapsed: true,
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
            collapsed: true,
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
            collapsed: true,
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
            collapsed: true,
        }),
        /isTargetInsideCurrentEditSubtree/,
    );
});

test('editing collapse toggle requires collapsed boolean', () => {
    assert.throws(
        () => shouldExitEditingBeforeCollapseToggle({
            isEditing: true,
            currentNoteId: 'note-a',
            targetNoteId: 'note-a',
            isTargetInsideCurrentEditSubtree: true,
        }),
        /collapsed/,
    );
});
