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

    return () => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.localStorage = originalLocalStorage;
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.HTMLButtonElement = originalHTMLButtonElement;
    };
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
