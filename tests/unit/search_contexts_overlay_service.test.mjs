import assert from 'node:assert/strict';
import test from 'node:test';

function createClassList(initialClasses = []) {
    const classes = new Set(initialClasses);
    return {
        add(name) {
            classes.add(name);
        },
        remove(name) {
            classes.delete(name);
        },
        contains(name) {
            return classes.has(name);
        },
    };
}

test('updateSearchContextsOverlayPlacement pins visible tab UI to bottom-left', async (t) => {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalHTMLElement = globalThis.HTMLElement;

    class FakeHTMLElement {}

    const searchContextsList = new FakeHTMLElement();
    searchContextsList.classList = createClassList();

    globalThis.HTMLElement = FakeHTMLElement;
    globalThis.document = {
        querySelector(selector) {
            if (selector === '#search-contexts-list') {
                return searchContextsList;
            }
            return null;
        },
    };
    globalThis.window = {
        getComputedStyle() {
            return { display: 'block' };
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.HTMLElement = originalHTMLElement;
    });

    const {
        isSearchContextsOverlayBottomLeft,
        updateSearchContextsOverlayPlacement,
    } = await import('../../app/static/js/modules/mode-manager/services/search-contexts-overlay-service.js');

    assert.equal(updateSearchContextsOverlayPlacement(), true);
    assert.equal(isSearchContextsOverlayBottomLeft(), true);
});

test('updateSearchContextsOverlayPlacement clears bottom-left marker when tab UI is hidden', async (t) => {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalHTMLElement = globalThis.HTMLElement;

    class FakeHTMLElement {}

    const searchContextsList = new FakeHTMLElement();
    searchContextsList.classList = createClassList(['search-contexts-list--bottom-left']);

    globalThis.HTMLElement = FakeHTMLElement;
    globalThis.document = {
        querySelector(selector) {
            if (selector === '#search-contexts-list') {
                return searchContextsList;
            }
            return null;
        },
    };
    globalThis.window = {
        getComputedStyle() {
            return { display: 'none' };
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.HTMLElement = originalHTMLElement;
    });

    const {
        isSearchContextsOverlayBottomLeft,
        updateSearchContextsOverlayPlacement,
    } = await import('../../app/static/js/modules/mode-manager/services/search-contexts-overlay-service.js');

    assert.equal(updateSearchContextsOverlayPlacement(), false);
    assert.equal(isSearchContextsOverlayBottomLeft(), false);
});
