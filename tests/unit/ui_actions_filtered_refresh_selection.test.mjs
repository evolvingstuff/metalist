import assert from 'node:assert/strict';
import test from 'node:test';

import { clearEditingStateForHiddenFilteredNote } from '../../app/static/js/modules/mode-manager/services/filtered-refresh-selection-service.js';

test('clearEditingStateForHiddenFilteredNote clears editing selection and editor chrome', () => {
    const calls = [];
    const modeContext = {
        isEditing: true,
        currentNoteId: 'note-1',
        currentContent: '<p>draft</p>',
        setCurrentContent(value) {
            calls.push(['setCurrentContent', value]);
            this.currentContent = value;
        },
        setEditing(value) {
            calls.push(['setEditing', value]);
            this.isEditing = value;
        },
        setCurrentNoteId(value) {
            calls.push(['setCurrentNoteId', value]);
            this.currentNoteId = value;
        },
    };

    clearEditingStateForHiddenFilteredNote({
        modeContext,
        detachEditorSurfaceFn() {
            calls.push(['detachEditorSurface']);
        },
        clearTagBarFn() {
            calls.push(['clearTagBar']);
        },
    });

    assert.equal(modeContext.isEditing, false);
    assert.equal(modeContext.currentNoteId, null);
    assert.equal(modeContext.currentContent, null);
    assert.deepEqual(calls, [
        ['setCurrentContent', null],
        ['detachEditorSurface'],
        ['clearTagBar'],
        ['setEditing', false],
        ['setCurrentNoteId', null],
    ]);
});
