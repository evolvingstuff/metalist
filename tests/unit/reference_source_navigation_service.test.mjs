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
    };
}

function createTab(searchQuery = '') {
    return {
        searchQuery,
        scrollY: 0,
        scrollAnchor: null,
        sortMode: 'normal',
        dateFilter: null,
    };
}

test('nested reference source entries expose and dismiss one temporary context at a time', async (t) => {
    const originalDocument = globalThis.document;
    const originalHTMLElement = globalThis.HTMLElement;
    const originalSessionStorage = globalThis.sessionStorage;

    class FakeHTMLElement {
        constructor() {
            this.hidden = true;
        }
    }

    const indicator = new FakeHTMLElement();
    globalThis.HTMLElement = FakeHTMLElement;
    globalThis.sessionStorage = createStorage();
    globalThis.document = {
        body: {
            classList: {
                add() {},
                remove() {},
            },
        },
        getElementById(id) {
            return id === 'reference-source-indicator' ? indicator : null;
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.sessionStorage = originalSessionStorage;
    });

    const { ModeContextInstance: ModeContext } = await import(
        '../../app/static/js/modules/mode-manager/mode-context.js'
    );
    const {
        isViewingReferenceSource,
        getActiveReferenceSourceQuery,
        popReferenceNavigationEntryForActiveTab,
        pushReferenceNavigationEntry,
        updateReferenceSourceIndicator,
    } = await import(
        '../../app/static/js/modules/mode-manager/services/reference-source-navigation-service.js'
    );

    ModeContext.hydrateTabState({
        activeTabId: 'source-1',
        tabs: {
            original: createTab('project'),
            'source-1': createTab('uuid-1'),
            'source-2': createTab('uuid-2'),
        },
        tabOrder: ['original', 'source-1', 'source-2'],
    }, { emitUpdate: false });
    pushReferenceNavigationEntry('original', 'source-1', 'uuid-1');
    assert.equal(isViewingReferenceSource(), true);
    assert.equal(getActiveReferenceSourceQuery(), 'uuid-1');
    assert.equal(indicator.hidden, false);

    ModeContext.hydrateTabState({
        activeTabId: 'source-2',
        tabs: {
            original: createTab('project'),
            'source-1': createTab('uuid-1'),
            'source-2': createTab('uuid-2'),
        },
        tabOrder: ['original', 'source-1', 'source-2'],
    }, { emitUpdate: false });
    pushReferenceNavigationEntry('source-1', 'source-2', 'uuid-2');
    assert.deepEqual(popReferenceNavigationEntryForActiveTab(), {
        fromTabId: 'source-1',
        toTabId: 'source-2',
        referenceQuery: 'uuid-2',
    });
    assert.equal(indicator.hidden, true);

    ModeContext.hydrateTabState({
        activeTabId: 'source-1',
        tabs: {
            original: createTab('project'),
            'source-1': createTab('uuid-1'),
        },
        tabOrder: ['original', 'source-1'],
    }, { emitUpdate: false });
    updateReferenceSourceIndicator();
    assert.equal(indicator.hidden, false);
    assert.deepEqual(popReferenceNavigationEntryForActiveTab(), {
        fromTabId: 'original',
        toTabId: 'source-1',
        referenceQuery: 'uuid-1',
    });
    assert.equal(indicator.hidden, true);

    await import('../../app/static/js/modules/mode-manager/services/infinite-scroll-service.js');
    await Promise.resolve();
});
