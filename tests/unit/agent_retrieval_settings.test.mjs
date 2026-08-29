import assert from 'node:assert/strict';
import test from 'node:test';

import {
    AGENT_RETRIEVAL_PREFERENCE_KEYS,
    DEFAULT_AGENT_RETRIEVAL_SETTINGS,
    readAgentRetrievalSettings,
    validateAgentRetrievalSettings,
} from '../../app/static/js/modules/ai-chat/agent-retrieval-settings.js';


test('agent retrieval settings use bounded defaults', () => {
    assert.deepEqual(readAgentRetrievalSettings(() => null), {
        maxNoteCharacters: 2000,
        maxPageCharacters: 20000,
        maxNotesPerPage: 50,
    });
    assert.equal(DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxNoteCharacters, 2000);
    assert.equal(DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxPageCharacters, 20000);
    assert.equal(DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxNotesPerPage, 50);
});


test('agent retrieval settings read namespace preference values', () => {
    const preferences = new Map([
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxNoteCharacters, '4000'],
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxPageCharacters, '30000'],
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxNotesPerPage, '3'],
    ]);

    assert.deepEqual(readAgentRetrievalSettings((key) => preferences.get(key) ?? null), {
        maxNoteCharacters: 4000,
        maxPageCharacters: 30000,
        maxNotesPerPage: 3,
    });
});


test('agent retrieval settings reject values outside bounded ranges', () => {
    assert.throws(
        () => validateAgentRetrievalSettings({
            maxNoteCharacters: 499,
            maxPageCharacters: 20000,
            maxNotesPerPage: 5,
        }),
        /500 to 10000/,
    );
    assert.throws(
        () => validateAgentRetrievalSettings({
            maxNoteCharacters: 8000,
            maxPageCharacters: 20000,
            maxNotesPerPage: 101,
        }),
        /1 to 100/,
    );
    assert.throws(
        () => validateAgentRetrievalSettings({
            maxNoteCharacters: 2000,
            maxPageCharacters: 4999,
            maxNotesPerPage: 50,
        }),
        /5000 to 100000/,
    );
});
