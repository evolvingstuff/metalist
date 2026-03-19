import assert from 'node:assert/strict';
import test from 'node:test';

import {
    getDuplicateTabCloneOptions,
    seedDuplicatedTabNoteHashes,
} from '../../app/static/js/modules/mode-manager/services/tab-duplication-service.js';

test('getDuplicateTabCloneOptions collects note hashes from DOM when source cache is empty', () => {
    const options = getDuplicateTabCloneOptions(0);
    assert.deepEqual(options, { collectNoteHashes: true });
});

test('seedDuplicatedTabNoteHashes leaves empty cloned DOM unseeded', () => {
    let cloneCalls = 0;
    let seedCalls = 0;

    const result = seedDuplicatedTabNoteHashes({
        sourceHashCount: 0,
        sourceTabId: 'source-tab',
        newTabId: 'new-tab',
        cloneResult: {
            cloned: true,
            nodeCount: 0,
            noteHashes: new Map(),
        },
        cloneTabNoteHashes() {
            cloneCalls += 1;
            return { cloned: true };
        },
        seedTabNoteHashes() {
            seedCalls += 1;
        },
    });

    assert.deepEqual(result, { seeded: false, strategy: 'empty-dom' });
    assert.equal(cloneCalls, 0);
    assert.equal(seedCalls, 0);
});

test('seedDuplicatedTabNoteHashes seeds from cloned DOM hashes when source cache is empty', () => {
    const noteHashes = new Map([
        ['note-1', 'hash-1'],
        ['note-2', 'hash-2'],
    ]);
    const seeded = [];

    const result = seedDuplicatedTabNoteHashes({
        sourceHashCount: 0,
        sourceTabId: 'source-tab',
        newTabId: 'new-tab',
        cloneResult: {
            cloned: true,
            nodeCount: 2,
            noteHashes,
        },
        cloneTabNoteHashes() {
            throw new Error('cloneTabNoteHashes should not be used when source cache is empty');
        },
        seedTabNoteHashes(tabId, hashes) {
            seeded.push({ tabId, hashes });
        },
    });

    assert.deepEqual(result, { seeded: true, strategy: 'seed-from-cloned-dom' });
    assert.equal(seeded.length, 1);
    assert.equal(seeded[0].tabId, 'new-tab');
    assert.equal(seeded[0].hashes, noteHashes);
});

test('seedDuplicatedTabNoteHashes clones existing cache when source hashes are present', () => {
    const cloneCalls = [];
    let seedCalls = 0;

    const result = seedDuplicatedTabNoteHashes({
        sourceHashCount: 3,
        sourceTabId: 'source-tab',
        newTabId: 'new-tab',
        cloneResult: {
            cloned: true,
            nodeCount: 3,
            noteHashes: null,
        },
        cloneTabNoteHashes(sourceTabId, newTabId) {
            cloneCalls.push({ sourceTabId, newTabId });
            return { cloned: true };
        },
        seedTabNoteHashes() {
            seedCalls += 1;
        },
    });

    assert.deepEqual(result, { seeded: true, strategy: 'clone-existing-cache' });
    assert.deepEqual(cloneCalls, [{ sourceTabId: 'source-tab', newTabId: 'new-tab' }]);
    assert.equal(seedCalls, 0);
});
