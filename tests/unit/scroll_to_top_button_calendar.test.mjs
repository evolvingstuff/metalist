import assert from 'node:assert/strict';
import test from 'node:test';

function installScrollButtonDom(t, calendarState) {
    if (!calendarState || typeof calendarState !== 'object') {
        throw new Error('installScrollButtonDom requires calendarState');
    }
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalSessionStorage = globalThis.sessionStorage;

    const buttonListeners = new Map();
    const panelListeners = new Map();
    const storage = new Map([
        ['metalist_client_id', 'test-client'],
        ['metalist_undo_context_epoch', '0'],
    ]);

    const button = {
        disabled: false,
        blurCount: 0,
        addEventListener(type, listener) {
            buttonListeners.set(type, listener);
        },
        blur() {
            this.blurCount += 1;
        },
        click() {
            if (this.disabled) {
                return;
            }
            const listener = buttonListeners.get('click');
            if (typeof listener === 'function') {
                listener();
            }
        },
    };

    const rhsPanel = {
        addEventListener(type, listener) {
            panelListeners.set(type, listener);
        },
        scroll() {
            const listener = panelListeners.get('scroll');
            if (typeof listener === 'function') {
                listener();
            }
        },
    };

    globalThis.window = {
        scrollY: 0,
        addEventListener() {},
        requestAnimationFrame(callback) {
            callback(0);
            return 1;
        },
        cancelAnimationFrame() {},
        matchMedia() {
            return { matches: true };
        },
        scrollTo() {},
    };

    globalThis.document = {
        getElementById(id) {
            if (id === 'scroll-to-top-button') {
                return button;
            }
            if (id === 'rhs-panel') {
                return rhsPanel;
            }
            return null;
        },
    };
    globalThis.sessionStorage = {
        getItem(key) {
            if (storage.has(key)) {
                return storage.get(key);
            }
            return null;
        },
        setItem(key, value) {
            storage.set(key, String(value));
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.sessionStorage = originalSessionStorage;
    });

    return { button, rhsPanel };
}

test('scroll-to-top button stays enabled at page top when RHS calendar is not newest', async (t) => {
    const calendarState = {
        pinnedToNewest: false,
        scrollCalls: 0,
    };
    const { button } = installScrollButtonDom(t, calendarState);
    const { initializeScrollToTopButton } = await import(
        '../../app/static/js/modules/mode-manager/services/scroll-to-top-service.js'
    );

    initializeScrollToTopButton({
        isCalendarPinnedToNewest() {
            return calendarState.pinnedToNewest;
        },
        scrollCalendarToNewest() {
            calendarState.scrollCalls += 1;
            calendarState.pinnedToNewest = true;
        },
    });

    assert.equal(button.disabled, false);

    button.click();

    assert.equal(calendarState.scrollCalls, 1);
    assert.equal(button.disabled, true);
    assert.equal(button.blurCount, 1);
});

test('scroll-to-top button enables after the RHS calendar scrolls away from newest', async (t) => {
    const calendarState = {
        pinnedToNewest: true,
        scrollCalls: 0,
    };
    const { button, rhsPanel } = installScrollButtonDom(t, calendarState);
    const { initializeScrollToTopButton } = await import(
        '../../app/static/js/modules/mode-manager/services/scroll-to-top-service.js'
    );

    initializeScrollToTopButton({
        isCalendarPinnedToNewest() {
            return calendarState.pinnedToNewest;
        },
        scrollCalendarToNewest() {
            calendarState.scrollCalls += 1;
            calendarState.pinnedToNewest = true;
        },
    });

    assert.equal(button.disabled, true);

    calendarState.pinnedToNewest = false;
    rhsPanel.scroll();

    assert.equal(button.disabled, false);
});
