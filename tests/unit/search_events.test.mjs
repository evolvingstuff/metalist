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

function installSearchEventsDom(t) {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalSessionStorage = globalThis.sessionStorage;
    const originalLocalStorage = globalThis.localStorage;
    const originalHTMLElement = globalThis.HTMLElement;
    const originalHTMLButtonElement = globalThis.HTMLButtonElement;

    const searchSuggestions = {
        hidden: true,
        style: {},
        innerHTML: '',
    };
    const searchValidationMessage = {
        hidden: true,
        textContent: '',
    };
    const notesContainer = {
        childNodes: [{ nodeType: 1 }],
        get firstChild() {
            return this.childNodes.length > 0 ? this.childNodes[0] : null;
        },
        replaceChildren() {
            this.childNodes = [];
        },
        removeChild(node) {
            const index = this.childNodes.indexOf(node);
            if (index >= 0) {
                this.childNodes.splice(index, 1);
            }
        },
    };

    globalThis.document = {
        activeElement: null,
        body: {
            classList: {
                add() {},
                remove() {},
            },
        },
        getElementById(id) {
            if (id === 'search-suggestions') {
                return searchSuggestions;
            }
            if (id === 'search-validation-message') {
                return searchValidationMessage;
            }
            if (id === 'notes-container') {
                return notesContainer;
            }
            return null;
        },
        addEventListener() {},
        removeEventListener() {},
    };
    globalThis.window = {
        addEventListener() {},
        removeEventListener() {},
        scrollTo() {},
    };
    globalThis.sessionStorage = createStorage();
    globalThis.localStorage = createStorage();
    globalThis.HTMLElement = class FakeHTMLElement {};
    globalThis.HTMLButtonElement = class FakeHTMLButtonElement extends globalThis.HTMLElement {};

    const restore = () => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.localStorage = originalLocalStorage;
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.HTMLButtonElement = originalHTMLButtonElement;
    };
    restore.notesContainer = notesContainer;
    return restore;
}

function createSearchInput(value) {
    return {
        value,
        selectionStart: value.length,
        selectionEnd: value.length,
        classList: {
            toggle() {},
        },
        setSelectionRange(start, end) {
            this.selectionStart = start;
            this.selectionEnd = end;
        },
    };
}

test('handleSearchInput updates search query even while loading', async (t) => {
    const restoreDom = installSearchEventsDom(t);

    const [{ handleSearchInput }, { cancelDebouncedSearchExecution }, { ModeContextInstance: ModeContext }] = await Promise.all([
        import('../../app/static/js/modules/mode-manager/events/search-events.js'),
        import('../../app/static/js/modules/mode-manager/services/search-debounce-service.js'),
        import('../../app/static/js/modules/mode-manager/mode-context.js'),
    ]);

    ModeContext.setSearchQuery('ML');
    ModeContext.setLoading(true);

    t.after(() => {
        cancelDebouncedSearchExecution();
        if (ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
        ModeContext.setSearchQuery('');
        restoreDom();
    });

    handleSearchInput({
        target: createSearchInput('ML3'),
    });

    assert.equal(ModeContext.searchQuery, 'ML3');
});

test('fresh search input clears same-query render cache and active DOM', async (t) => {
    const restoreDom = installSearchEventsDom(t);

    const [{ resetActiveTabForSearchExecution }, { ModeContextInstance: ModeContext }] = await Promise.all([
        import('../../app/static/js/modules/mode-manager/events/search-events.js'),
        import('../../app/static/js/modules/mode-manager/mode-context.js'),
    ]);
    const tabId = ModeContext.activeTabId;

    t.after(() => {
        ModeContext.clearTabViewCache(tabId);
        restoreDom();
    });

    ModeContext.clearTabViewCache(tabId);
    ModeContext.setExecutedSearchQuery('journal', tabId);
    ModeContext.seedTabNoteHashes(tabId, new Map([
        ['root-a', 'hash-a'],
        ['root-b', 'hash-b'],
    ]));

    resetActiveTabForSearchExecution('journal', { isFreshSearchInput: false });
    assert.equal(ModeContext.getTabNoteHashCount(tabId), 2);
    assert.equal(restoreDom.notesContainer.childNodes.length, 1);

    resetActiveTabForSearchExecution('journal', { isFreshSearchInput: true });
    assert.equal(ModeContext.getTabNoteHashCount(tabId), 0);
    assert.equal(restoreDom.notesContainer.childNodes.length, 0);
});
