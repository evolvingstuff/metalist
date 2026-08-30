import assert from 'node:assert/strict';
import test from 'node:test';

import {
    AGENT_RETRIEVAL_PREFERENCE_KEYS,
    DEFAULT_AGENT_RETRIEVAL_SETTINGS,
    DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS,
    OPENAI_AGENT_RETRIEVAL_PREFERENCE_KEYS,
    readAgentRetrievalSettings,
    validateAgentRetrievalSettings,
} from '../../app/static/js/modules/ai-chat/agent-retrieval-settings.js';


test('agent retrieval settings use bounded defaults', () => {
    assert.deepEqual(readAgentRetrievalSettings(() => null, 'ollama'), {
        maxNoteCharacters: 2000,
        maxPageCharacters: 20000,
        maxNotesPerPage: 50,
        maxPageApproximateTokens: 5000,
        maxRankedTagsPerPage: 50,
        maxWorkingSummaryCharacters: 8000,
    });
    assert.equal(DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxNoteCharacters, 2000);
    assert.equal(DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxPageCharacters, 20000);
    assert.equal(DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxNotesPerPage, 50);
    assert.equal(DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxPageApproximateTokens, 5000);
    assert.equal(DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxRankedTagsPerPage, 50);
    assert.equal(DEFAULT_AGENT_RETRIEVAL_SETTINGS.maxWorkingSummaryCharacters, 8000);
    assert.deepEqual(
        readAgentRetrievalSettings(() => null, 'openai'),
        DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS,
    );
    assert.equal(DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS.maxPageApproximateTokens, 24000);
});


test('agent retrieval settings read namespace preference values', () => {
    const preferences = new Map([
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxNoteCharacters, '4000'],
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxPageCharacters, '30000'],
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxNotesPerPage, '3'],
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxPageApproximateTokens, '7000'],
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxRankedTagsPerPage, '25'],
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxWorkingSummaryCharacters, '12000'],
    ]);

    assert.deepEqual(readAgentRetrievalSettings(
        (key) => preferences.get(key) ?? null,
        'ollama',
    ), {
        maxNoteCharacters: 4000,
        maxPageCharacters: 30000,
        maxNotesPerPage: 3,
        maxPageApproximateTokens: 7000,
        maxRankedTagsPerPage: 25,
        maxWorkingSummaryCharacters: 12000,
    });
});


test('agent retrieval settings keep provider preferences independent', () => {
    const preferences = new Map([
        [AGENT_RETRIEVAL_PREFERENCE_KEYS.maxPageApproximateTokens, '7000'],
        [OPENAI_AGENT_RETRIEVAL_PREFERENCE_KEYS.maxNoteCharacters, '6000'],
        [OPENAI_AGENT_RETRIEVAL_PREFERENCE_KEYS.maxPageCharacters, '80000'],
        [OPENAI_AGENT_RETRIEVAL_PREFERENCE_KEYS.maxNotesPerPage, '75'],
        [OPENAI_AGENT_RETRIEVAL_PREFERENCE_KEYS.maxPageApproximateTokens, '20000'],
        [OPENAI_AGENT_RETRIEVAL_PREFERENCE_KEYS.maxRankedTagsPerPage, '125'],
        [OPENAI_AGENT_RETRIEVAL_PREFERENCE_KEYS.maxWorkingSummaryCharacters, '24000'],
    ]);

    assert.equal(
        readAgentRetrievalSettings(
            (key) => preferences.get(key) ?? null,
            'ollama',
        ).maxPageApproximateTokens,
        7000,
    );
    assert.deepEqual(readAgentRetrievalSettings(
        (key) => preferences.get(key) ?? null,
        'openai',
    ), {
        maxNoteCharacters: 6000,
        maxPageCharacters: 80000,
        maxNotesPerPage: 75,
        maxPageApproximateTokens: 20000,
        maxRankedTagsPerPage: 125,
        maxWorkingSummaryCharacters: 24000,
    });
});


test('agent retrieval settings reject values outside bounded ranges', () => {
    assert.throws(
        () => validateAgentRetrievalSettings({
            maxNoteCharacters: 499,
            maxPageCharacters: 20000,
            maxNotesPerPage: 5,
            maxPageApproximateTokens: 5000,
            maxRankedTagsPerPage: 50,
            maxWorkingSummaryCharacters: 8000,
        }),
        /500 to 10000/,
    );
    assert.throws(
        () => validateAgentRetrievalSettings({
            maxNoteCharacters: 8000,
            maxPageCharacters: 20000,
            maxNotesPerPage: 101,
            maxPageApproximateTokens: 5000,
            maxRankedTagsPerPage: 50,
            maxWorkingSummaryCharacters: 8000,
        }),
        /1 to 100/,
    );
    assert.throws(
        () => validateAgentRetrievalSettings({
            maxNoteCharacters: 2000,
            maxPageCharacters: 4999,
            maxNotesPerPage: 50,
            maxPageApproximateTokens: 5000,
            maxRankedTagsPerPage: 50,
            maxWorkingSummaryCharacters: 8000,
        }),
        /5000 to 100000/,
    );
    assert.throws(
        () => validateAgentRetrievalSettings({
            maxNoteCharacters: 2000,
            maxPageCharacters: 20000,
            maxNotesPerPage: 50,
            maxPageApproximateTokens: 5000,
            maxRankedTagsPerPage: 201,
            maxWorkingSummaryCharacters: 8000,
        }),
        /1 to 200/,
    );
    assert.throws(
        () => validateAgentRetrievalSettings({
            maxNoteCharacters: 2000,
            maxPageCharacters: 20000,
            maxNotesPerPage: 50,
            maxPageApproximateTokens: 5000,
            maxRankedTagsPerPage: 50,
            maxWorkingSummaryCharacters: 1999,
        }),
        /2000 to 32000/,
    );
    assert.throws(
        () => validateAgentRetrievalSettings({
            maxNoteCharacters: 2000,
            maxPageCharacters: 20000,
            maxNotesPerPage: 50,
            maxPageApproximateTokens: 24001,
            maxRankedTagsPerPage: 50,
            maxWorkingSummaryCharacters: 8000,
        }),
        /500 to 24000/,
    );
});
