import assert from 'node:assert/strict';
import test from 'node:test';

function installLinkContextDom(t) {
    const originalHTMLElement = globalThis.HTMLElement;
    const originalHTMLAnchorElement = globalThis.HTMLAnchorElement;
    const originalNavigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
    const originalWindowDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'window');

    class FakeHTMLElement {
        closest() {
            return null;
        }
    }

    class FakeAnchorElement extends FakeHTMLElement {
        constructor(options) {
            super();
            this.href = options.href;
            this.rawHref = options.rawHref;
        }

        closest(selector) {
            if (selector === 'a[href]') {
                return this;
            }
            return null;
        }

        getAttribute(name) {
            if (name === 'href') {
                return this.rawHref;
            }
            return null;
        }
    }

    globalThis.HTMLElement = FakeHTMLElement;
    globalThis.HTMLAnchorElement = FakeAnchorElement;
    Object.defineProperty(globalThis, 'navigator', {
        value: {
            clipboard: {
                async writeText() {},
            },
        },
        configurable: true,
        writable: true,
    });
    Object.defineProperty(globalThis, 'window', {
        value: {
            open() {
                return null;
            },
        },
        configurable: true,
        writable: true,
    });

    t.after(() => {
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.HTMLAnchorElement = originalHTMLAnchorElement;
        if (originalNavigatorDescriptor) {
            Object.defineProperty(globalThis, 'navigator', originalNavigatorDescriptor);
        } else {
            delete globalThis.navigator;
        }
        if (originalWindowDescriptor) {
            Object.defineProperty(globalThis, 'window', originalWindowDescriptor);
        } else {
            delete globalThis.window;
        }
    });

    return { FakeAnchorElement };
}

test('resolveLinkContextFromElement returns normalized anchor href', async (t) => {
    const { FakeAnchorElement } = installLinkContextDom(t);
    const { resolveLinkContextFromElement } = await import(
        '../../app/static/js/modules/mode-manager/services/link-context-menu-action-service.js'
    );
    const anchor = new FakeAnchorElement({
        rawHref: '/docs',
        href: 'https://metalist.local/docs',
    });

    assert.deepEqual(resolveLinkContextFromElement(anchor), {
        href: 'https://metalist.local/docs',
    });
});

test('resolveLinkContextFromElement ignores hash-only anchors', async (t) => {
    const { FakeAnchorElement } = installLinkContextDom(t);
    const { resolveLinkContextFromElement } = await import(
        '../../app/static/js/modules/mode-manager/services/link-context-menu-action-service.js'
    );
    const anchor = new FakeAnchorElement({
        rawHref: '#note-123',
        href: 'https://metalist.local/#note-123',
    });

    assert.equal(resolveLinkContextFromElement(anchor), null);
});

test('copyLinkToClipboard writes href text', async (t) => {
    installLinkContextDom(t);
    let copiedText = null;
    globalThis.navigator.clipboard.writeText = async (value) => {
        copiedText = value;
    };
    const { copyLinkToClipboard } = await import(
        '../../app/static/js/modules/mode-manager/services/link-context-menu-action-service.js'
    );

    await copyLinkToClipboard({ href: 'https://example.com/article' });

    assert.equal(copiedText, 'https://example.com/article');
});

test('openLinkInNewTabFromContext opens href in another tab', async (t) => {
    installLinkContextDom(t);
    let opened = null;
    globalThis.window.open = (url, target, features) => {
        opened = { url, target, features };
        return null;
    };
    const { openLinkInNewTabFromContext } = await import(
        '../../app/static/js/modules/mode-manager/services/link-context-menu-action-service.js'
    );

    await openLinkInNewTabFromContext({ href: 'https://example.com/article' });

    assert.deepEqual(opened, {
        url: 'https://example.com/article',
        target: '_blank',
        features: 'noopener,noreferrer',
    });
});
