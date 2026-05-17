import assert from 'node:assert/strict';
import test from 'node:test';

function createStorage() {
    const entries = new Map();
    return {
        getItem(key) {
            return entries.has(key) ? entries.get(key) : null;
        },
        setItem(key, value) {
            entries.set(key, String(value));
        },
        removeItem(key) {
            entries.delete(key);
        },
        clear() {
            entries.clear();
        },
    };
}

function installTabStateGlobals(t) {
    const originalSessionStorage = globalThis.sessionStorage;
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;

    globalThis.sessionStorage = createStorage();
    globalThis.document = {
        querySelector() {
            return null;
        },
        getElementById() {
            return {
                querySelectorAll() {
                    return [];
                },
            };
        },
    };
    globalThis.window = {
        addEventListener() {},
        setInterval() {
            return 1;
        },
        clearTimeout() {},
        setTimeout(callback) {
            callback();
            return 1;
        },
        innerHeight: 800,
        scrollY: 0,
    };

    t.after(() => {
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
    });
}

function makeAnchor(overrides) {
    const base = {
        anchorId: 'root-a',
        anchorBias: 'top',
        intraOffset: 12,
        beltPrev: ['root-prev'],
        beltNext: ['root-next'],
        anchorSortKey: { domIndex: 1 },
    };
    return { ...base, ...overrides };
}

test('scroll anchor comparison treats repeated null anchors as unchanged', async (t) => {
    installTabStateGlobals(t);
    const { areScrollAnchorsEqual } = await import('../../app/static/js/modules/mode-manager/services/scroll-anchor-service.js');

    assert.equal(areScrollAnchorsEqual(null, null), true);
    assert.equal(areScrollAnchorsEqual(makeAnchor({}), null), false);
    assert.equal(areScrollAnchorsEqual(null, makeAnchor({})), false);
});

test('scroll anchor comparison catches structural changes without relying on object identity', async (t) => {
    installTabStateGlobals(t);
    const { areScrollAnchorsEqual } = await import('../../app/static/js/modules/mode-manager/services/scroll-anchor-service.js');

    assert.equal(areScrollAnchorsEqual(makeAnchor({}), makeAnchor({})), true);
    assert.equal(areScrollAnchorsEqual(makeAnchor({ intraOffset: 12 }), makeAnchor({ intraOffset: 13 })), false);
    assert.equal(areScrollAnchorsEqual(makeAnchor({ beltNext: ['root-next'] }), makeAnchor({ beltNext: ['other-root'] })), false);
});
