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

function installModeContextGlobals(t) {
    const originalSessionStorage = globalThis.sessionStorage;
    const originalDocument = globalThis.document;
    const originalPerformance = globalThis.performance;

    globalThis.sessionStorage = createStorage();
    globalThis.document = {
        body: {
            classList: {
                add() {},
                remove() {},
            },
        },
    };
    globalThis.performance = {
        now() {
            return 0;
        },
    };

    t.after(() => {
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.document = originalDocument;
        globalThis.performance = originalPerformance;
    });
}

test('ModeContext scalar setters reject same-value writes', async (t) => {
    installModeContextGlobals(t);
    const { ModeContextInstance: ModeContext } = await import('../../app/static/js/modules/mode-manager/mode-context.js');

    ModeContext.setSearchQuery('strict-state-test');
    assert.throws(
        () => ModeContext.setSearchQuery('strict-state-test'),
        /Redundant state change: searchQuery is already strict-state-test/
    );

    ModeContext.setLastUpdateUUID('uuid-strict-state-test');
    assert.throws(
        () => ModeContext.setLastUpdateUUID('uuid-strict-state-test'),
        /Redundant state change: lastUpdateUUID is already uuid-strict-state-test/
    );
});

test('ModeContext modal stack uses strict mutators instead of direct array mutation', async (t) => {
    installModeContextGlobals(t);
    const { ModeContextInstance: ModeContext } = await import('../../app/static/js/modules/mode-manager/mode-context.js');

    ModeContext.pushModal('strictModal');
    assert.equal(ModeContext.topModal, 'strictModal');
    assert.deepEqual(ModeContext.modalStack, ['strictModal']);
    assert.throws(
        () => ModeContext.pushModal('strictModal'),
        /Redundant state change: modalStack already has strictModal on top/
    );
    assert.throws(
        () => ModeContext.modalStack.push('directMutation'),
        /Cannot add property/
    );

    ModeContext.removeModal('strictModal');
    assert.equal(ModeContext.topModal, null);
    assert.deepEqual(ModeContext.modalStack, []);
    assert.throws(
        () => ModeContext.removeModal('strictModal'),
        /Redundant state change: modalStack does not contain strictModal/
    );
});
