import assert from 'node:assert/strict';
import test from 'node:test';

import { clearSelectionStateForDeselect } from '../../app/static/js/modules/mode-manager/services/deselect-selection-state-service.js';

function createStrictEditingState(currentContent) {
    const calls = [];
    const modeContext = {
        isEditing: true,
        currentNoteId: 'note-1',
        currentContent,
        setEditing(value) {
            assert.notEqual(this.isEditing, value, 'setEditing received a redundant write');
            calls.push(['setEditing', value]);
            this.isEditing = value;
        },
        setCurrentNoteId(value) {
            assert.notEqual(this.currentNoteId, value, 'setCurrentNoteId received a redundant write');
            calls.push(['setCurrentNoteId', value]);
            this.currentNoteId = value;
        },
        setCurrentContent(value) {
            assert.notEqual(this.currentContent, value, 'setCurrentContent received a redundant write');
            calls.push(['setCurrentContent', value]);
            this.currentContent = value;
        },
    };
    return { calls, modeContext };
}

test('deselecting does not clear currentContent twice when it is already null', () => {
    const { calls, modeContext } = createStrictEditingState(null);

    clearSelectionStateForDeselect(modeContext);

    assert.equal(modeContext.isEditing, false);
    assert.equal(modeContext.currentNoteId, null);
    assert.equal(modeContext.currentContent, null);
    assert.deepEqual(calls, [
        ['setEditing', false],
        ['setCurrentNoteId', null],
    ]);
});

test('deselecting clears non-null currentContent', () => {
    const { calls, modeContext } = createStrictEditingState('<div>draft</div>');

    clearSelectionStateForDeselect(modeContext);

    assert.equal(modeContext.isEditing, false);
    assert.equal(modeContext.currentNoteId, null);
    assert.equal(modeContext.currentContent, null);
    assert.deepEqual(calls, [
        ['setEditing', false],
        ['setCurrentNoteId', null],
        ['setCurrentContent', null],
    ]);
});
