import assert from 'node:assert/strict';
import test from 'node:test';

function installBrowserStorage(t) {
    const originalSessionStorage = globalThis.sessionStorage;
    const originalLocalStorage = globalThis.localStorage;
    const originalWindow = globalThis.window;

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

    globalThis.sessionStorage = createStorage();
    globalThis.localStorage = createStorage();
    globalThis.window = {};

    t.after(() => {
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.localStorage = originalLocalStorage;
        globalThis.window = originalWindow;
    });
}

test('resolveCanCollapseFromDataset trusts only server isCollapsible flag', async (t) => {
    installBrowserStorage(t);
    const { resolveCanCollapseFromDataset } = await import(
        '../../app/static/js/modules/mode-manager/services/collapse-affordance-service.js'
    );

    assert.equal(resolveCanCollapseFromDataset({ isCollapsible: 'true' }), true);
    assert.equal(resolveCanCollapseFromDataset({ isCollapsible: 'false' }), false);
    assert.equal(resolveCanCollapseFromDataset({}), false);
});
