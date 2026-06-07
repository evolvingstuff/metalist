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

function createFakeElement({
    classNames = [],
    innerHTML = '',
    rect = { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 },
} = {}) {
    return {
        classList: createClassList(classNames),
        innerHTML,
        style: {},
        getBoundingClientRect() {
            return rect;
        },
    };
}

function installOverlayDom(t, {
    isTabUiEnabled,
    tabRowsHtml = '<button>Default</button>',
    searchContextsRect = { left: 0, right: 220, top: 0, bottom: 160, width: 220, height: 160 },
    hoverZoneRect = { left: 20, right: 100, top: 10, bottom: 44, width: 80, height: 34 },
    controlsRect = { left: 120, right: 680, top: 0, bottom: 60, width: 560, height: 60 },
} = {}) {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalHTMLElement = globalThis.HTMLElement;

    class FakeHTMLElement {}

    const body = new FakeHTMLElement();
    Object.assign(body, createFakeElement({
        classNames: isTabUiEnabled ? ['pref-show-tab-ui'] : [],
    }));
    const searchContextsList = new FakeHTMLElement();
    Object.assign(searchContextsList, createFakeElement({
        innerHTML: tabRowsHtml,
        rect: searchContextsRect,
    }));
    const hoverZone = new FakeHTMLElement();
    Object.assign(hoverZone, createFakeElement({ rect: hoverZoneRect }));
    const controls = new FakeHTMLElement();
    Object.assign(controls, createFakeElement({ rect: controlsRect }));

    globalThis.HTMLElement = FakeHTMLElement;
    globalThis.document = {
        body,
        querySelector(selector) {
            if (selector === '#search-contexts-list') {
                return searchContextsList;
            }
            if (selector === '#tab-hover-zone') {
                return hoverZone;
            }
            if (selector === '.controls') {
                return controls;
            }
            return null;
        },
    };
    globalThis.window = {
        innerWidth: 1024,
        getComputedStyle() {
            return { display: searchContextsList.style.display || 'none' };
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.HTMLElement = originalHTMLElement;
    });

    return { searchContextsList };
}

test('showSearchContextsOverlay positions visible tab popover from controls and hover zone', async (t) => {
    const { searchContextsList } = installOverlayDom(t, { isTabUiEnabled: true });

    const {
        isSearchContextsOverlayBottomLeft,
        showSearchContextsOverlay,
    } = await import('../../app/static/js/modules/mode-manager/services/search-contexts-overlay-service.js');

    assert.equal(showSearchContextsOverlay(), true);
    assert.equal(searchContextsList.style.display, 'block');
    assert.equal(searchContextsList.style.left, '120px');
    assert.equal(searchContextsList.style.top, '50px');
    assert.equal(searchContextsList.style.right, 'auto');
    assert.equal(searchContextsList.style.bottom, 'auto');
    assert.equal(searchContextsList.classList.contains('search-contexts-list--hover'), true);
    assert.equal(isSearchContextsOverlayBottomLeft(), false);
});

test('updateSearchContextsOverlayPlacement hides tab popover when tab UI is disabled', async (t) => {
    const { searchContextsList } = installOverlayDom(t, { isTabUiEnabled: false });
    searchContextsList.style.display = 'block';

    const {
        isSearchContextsOverlayBottomLeft,
        updateSearchContextsOverlayPlacement,
    } = await import('../../app/static/js/modules/mode-manager/services/search-contexts-overlay-service.js');

    assert.equal(updateSearchContextsOverlayPlacement(), false);
    assert.equal(searchContextsList.style.display, 'none');
    assert.equal(isSearchContextsOverlayBottomLeft(), false);
});
