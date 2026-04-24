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
    };
}

function installSuggestionsContainer(t, container) {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalSessionStorage = globalThis.sessionStorage;
    const originalLocalStorage = globalThis.localStorage;
    globalThis.document = {
        getElementById(id) {
            if (id === 'search-suggestions') {
                return container;
            }
            return null;
        },
    };
    globalThis.window = {};
    globalThis.sessionStorage = createStorage();
    globalThis.localStorage = createStorage();

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.localStorage = originalLocalStorage;
    });
}

async function importSearchSuggestionsService() {
    return await import('../../app/static/js/modules/mode-manager/services/search-suggestions-service.js');
}

test('hides visible search suggestions when a note is hovered during search mode', async (t) => {
    const container = {
        hidden: false,
        style: { display: 'flex' },
        innerHTML: '<button class="search-suggestion">work</button>',
    };
    installSuggestionsContainer(t, container);
    const { hideSearchSuggestionsForSearchContextHover } = await importSearchSuggestionsService();

    const didHide = hideSearchSuggestionsForSearchContextHover({
        isSearching: true,
        noteId: 'note-1',
    });

    assert.equal(didHide, true);
    assert.equal(container.hidden, true);
    assert.equal(container.style.display, 'none');
    assert.equal(container.innerHTML, '');
});

test('does not hide search suggestions for note hover outside search mode', async (t) => {
    const container = {
        hidden: false,
        style: { display: 'flex' },
        innerHTML: '<button class="search-suggestion">work</button>',
    };
    installSuggestionsContainer(t, container);
    const { hideSearchSuggestionsForSearchContextHover } = await importSearchSuggestionsService();

    const didHide = hideSearchSuggestionsForSearchContextHover({
        isSearching: false,
        noteId: 'note-1',
    });

    assert.equal(didHide, false);
    assert.equal(container.hidden, false);
    assert.equal(container.style.display, 'flex');
    assert.equal(container.innerHTML, '<button class="search-suggestion">work</button>');
});

test('does not re-hide search suggestions that are already hidden', async (t) => {
    const container = {
        hidden: true,
        style: { display: 'none' },
        innerHTML: '',
    };
    installSuggestionsContainer(t, container);
    const { hideSearchSuggestionsForSearchContextHover } = await importSearchSuggestionsService();

    const didHide = hideSearchSuggestionsForSearchContextHover({
        isSearching: true,
        noteId: 'note-1',
    });

    assert.equal(didHide, false);
    assert.equal(container.hidden, true);
    assert.equal(container.style.display, 'none');
    assert.equal(container.innerHTML, '');
});
