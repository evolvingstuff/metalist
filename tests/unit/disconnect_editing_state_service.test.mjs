import assert from 'node:assert/strict';
import test from 'node:test';

import {
    clearEditingStateForDisconnect,
} from '../../app/static/js/modules/disconnect-editing-state-service.js';


test('disconnect cleanup accepts the note-selection transition with null content', () => {
    const calls = [];
    const modeContext = {
        isEditing: true,
        currentNoteId: 'note-1',
        currentContent: null,
        setEditing(value) {
            calls.push(['editing', value]);
        },
        setCurrentNoteId(value) {
            calls.push(['currentNoteId', value]);
        },
        setCurrentContent() {
            throw new Error('setCurrentContent must not receive a redundant null write');
        },
    };

    assert.equal(clearEditingStateForDisconnect(modeContext), true);
    assert.deepEqual(calls, [
        ['editing', false],
        ['currentNoteId', null],
    ]);
});


test('disconnect cleanup clears loaded edit content when present', () => {
    const calls = [];
    const modeContext = {
        isEditing: true,
        currentNoteId: 'note-1',
        currentContent: '<p>Draft</p>',
        setEditing(value) {
            calls.push(['editing', value]);
        },
        setCurrentNoteId(value) {
            calls.push(['currentNoteId', value]);
        },
        setCurrentContent(value) {
            calls.push(['currentContent', value]);
        },
    };

    assert.equal(clearEditingStateForDisconnect(modeContext), true);
    assert.deepEqual(calls, [
        ['editing', false],
        ['currentNoteId', null],
        ['currentContent', null],
    ]);
});
