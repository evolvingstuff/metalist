import assert from 'node:assert/strict';
import test from 'node:test';

function createStorage() {
    const entries = new Map();
    return {
        getItem: (key) => entries.has(key) ? entries.get(key) : null,
        setItem: (key, value) => entries.set(key, String(value)),
        removeItem: (key) => entries.delete(key),
    };
}

globalThis.sessionStorage = createStorage();
globalThis.localStorage = createStorage();
globalThis.window = {};

const { NotesAPI } = await import('../../app/static/js/modules/api-client.js');
const { ModeContextInstance: ModeContext } = await import(
    '../../app/static/js/modules/mode-manager/mode-context.js'
);
const {
    primeActiveSearchInteractionState,
    recordNoteInteractionIfNew,
    resetNoteInteractionStateForTests,
} = await import('../../app/static/js/modules/mode-manager/services/search-interaction-service.js');


test('note engagement deduplicates edit, expand, command, and full screen in one navigation flow', async (t) => {
    const originalRecordNoteInteraction = NotesAPI.recordNoteInteraction;
    const originalQuery = ModeContext._tabExecutedSearchQuery['0'];
    const calls = [];
    NotesAPI.recordNoteInteraction = async (noteId, interactionType) => {
        calls.push({ noteId, interactionType });
        return { credited: true };
    };
    ModeContext._tabExecutedSearchQuery['0'] = 'shortcut';
    resetNoteInteractionStateForTests();
    t.after(() => {
        NotesAPI.recordNoteInteraction = originalRecordNoteInteraction;
        ModeContext._tabExecutedSearchQuery['0'] = originalQuery;
        resetNoteInteractionStateForTests();
    });

    assert.equal(await recordNoteInteractionIfNew('note-1', 'edit'), true);
    assert.equal(await recordNoteInteractionIfNew('note-1', 'expand'), false);
    assert.equal(await recordNoteInteractionIfNew('note-1', 'command'), false);
    assert.equal(await recordNoteInteractionIfNew('note-1', 'fullscreen'), false);
    assert.deepEqual(calls, [{ noteId: 'note-1', interactionType: 'edit' }]);

    assert.equal(await recordNoteInteractionIfNew('note-2', 'expand'), true);
    assert.equal(await recordNoteInteractionIfNew('note-1', 'command'), true);
    assert.deepEqual(calls, [
        { noteId: 'note-1', interactionType: 'edit' },
        { noteId: 'note-2', interactionType: 'expand' },
        { noteId: 'note-1', interactionType: 'command' },
    ]);
});


test('a new executed search starts a new engagement flow for the same note', async (t) => {
    const originalRecordNoteInteraction = NotesAPI.recordNoteInteraction;
    const originalQuery = ModeContext._tabExecutedSearchQuery['0'];
    let callCount = 0;
    NotesAPI.recordNoteInteraction = async () => {
        callCount += 1;
        return { credited: true };
    };
    ModeContext._tabExecutedSearchQuery['0'] = 'shortcut';
    resetNoteInteractionStateForTests();
    t.after(() => {
        NotesAPI.recordNoteInteraction = originalRecordNoteInteraction;
        ModeContext._tabExecutedSearchQuery['0'] = originalQuery;
        resetNoteInteractionStateForTests();
    });

    await recordNoteInteractionIfNew('note-1', 'command');
    ModeContext._tabExecutedSearchQuery['0'] = 'shortcut @shell';
    primeActiveSearchInteractionState();
    await recordNoteInteractionIfNew('note-1', 'command');

    assert.equal(callCount, 2);
});
