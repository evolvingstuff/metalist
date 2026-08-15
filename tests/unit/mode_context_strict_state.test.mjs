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

test('ModeContext notifies listeners when an executable search query is committed', async (t) => {
    installModeContextGlobals(t);
    const { ModeContextInstance: ModeContext } = await import('../../app/static/js/modules/mode-manager/mode-context.js');
    const notifications = [];
    const listener = (property, value) => {
        notifications.push({ property, value });
    };
    ModeContext.addListener(listener);
    t.after(() => {
        ModeContext.removeListener(listener);
    });

    ModeContext.setExecutedSearchQuery('committed-search-test');

    assert.deepEqual(notifications, [
        { property: 'executedSearchQuery', value: 'committed-search-test' },
    ]);
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

test('ModeContext keeps the untagged view outside persisted tab state', async (t) => {
    installModeContextGlobals(t);
    const { ModeContextInstance: ModeContext } = await import('../../app/static/js/modules/mode-manager/mode-context.js');

    ModeContext.setUntaggedView(true);
    t.after(() => {
        if (ModeContext.isUntaggedView) {
            ModeContext.setUntaggedView(false);
        }
    });

    const serializedTabState = ModeContext.getTabStatePayload();

    assert.equal(ModeContext.isUntaggedView, true);
    assert.equal(Object.hasOwn(serializedTabState, 'isUntaggedView'), false);
    for (const tab of Object.values(serializedTabState.tabs)) {
        assert.equal(Object.hasOwn(tab, 'isUntaggedView'), false);
    }
});
