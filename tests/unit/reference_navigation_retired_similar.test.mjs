import assert from 'node:assert/strict';
import test from 'node:test';


const ORIGIN_SCOPE = { scopeTabId: 'original', searchQuery: 'project', sortMode: 'normal', isUntaggedView: false };

// Reported: after the similar-notes view was removed, a browser tab that still held one
// in its session storage stopped MetaList on reload.
test('saved entries of unknown kinds of view (like the removed similar-notes view) are dropped on reload', async (t) => {
    const originalSessionStorage = globalThis.sessionStorage;
    globalThis.sessionStorage = { getItem: () => null, setItem() {}, removeItem() {} };
    t.after(() => {
        globalThis.sessionStorage = originalSessionStorage;
    });
    const { parseStoredReferenceNavigationStack } = await import(
        '../../app/static/js/modules/mode-manager/services/reference-source-navigation-service.js'
    );
    const stored = JSON.stringify([
        { fromTabId: 'original', toTabId: 'refs', referenceQuery: 'id-1', originScope: ORIGIN_SCOPE, viewKind: 'source' },
        { fromTabId: 'original', toTabId: 'similar', referenceQuery: 'id-2 OR id-3', originScope: ORIGIN_SCOPE,
            viewKind: 'similar', title: 'Mamba notes' },
    ]);
    const entries = parseStoredReferenceNavigationStack(stored);
    assert.deepEqual(entries.map((entry) => entry.toTabId), ['refs']);
    // Any kind of view this version does not know is dropped the same way.
    assert.deepEqual(parseStoredReferenceNavigationStack(JSON.stringify([
        { fromTabId: 'a', toTabId: 'b', referenceQuery: 'q', originScope: ORIGIN_SCOPE, viewKind: 'unknown' },
    ])), []);
});
