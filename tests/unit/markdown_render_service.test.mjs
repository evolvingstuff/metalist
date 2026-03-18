import assert from 'node:assert/strict';
import test from 'node:test';

import {
    applyMarkdownLinkTargetPolicy,
    ensureAnchorOpensInNewTab,
    ensureAnchorsOpenInNewTabs,
    ensureMarkdownLinkTokenOpensInNewTab,
} from '../../app/static/js/modules/mode-manager/services/markdown-render-service.js';

function createFakeLinkToken(initialAttrs) {
    return {
        attrs: initialAttrs.map(([name, value]) => [name, value]),
        attrIndex(name) {
            return this.attrs.findIndex((entry) => entry[0] === name);
        },
        attrPush(entry) {
            this.attrs.push(entry);
        },
    };
}

function createFakeAnchor(initialAttributes = {}) {
    const attributes = new Map(Object.entries(initialAttributes));
    return {
        getAttribute(name) {
            return attributes.has(name) ? attributes.get(name) : null;
        },
        setAttribute(name, value) {
            attributes.set(name, value);
        },
        snapshot() {
            return Object.fromEntries(attributes.entries());
        },
    };
}

test('ensureMarkdownLinkTokenOpensInNewTab adds target and rel attrs', () => {
    const token = createFakeLinkToken([['href', 'https://example.com']]);

    ensureMarkdownLinkTokenOpensInNewTab(token);

    assert.deepEqual(token.attrs, [
        ['href', 'https://example.com'],
        ['target', '_blank'],
        ['rel', 'noopener noreferrer'],
    ]);
});

test('ensureMarkdownLinkTokenOpensInNewTab merges rel and replaces target', () => {
    const token = createFakeLinkToken([
        ['href', 'https://example.com'],
        ['target', '_self'],
        ['rel', 'nofollow'],
    ]);

    ensureMarkdownLinkTokenOpensInNewTab(token);

    assert.deepEqual(token.attrs, [
        ['href', 'https://example.com'],
        ['target', '_blank'],
        ['rel', 'nofollow noopener noreferrer'],
    ]);
});

test('applyMarkdownLinkTargetPolicy wraps link_open rule', () => {
    const renderer = {
        renderer: {
            rules: {},
        },
    };
    applyMarkdownLinkTargetPolicy(renderer);

    const token = createFakeLinkToken([['href', 'https://example.com']]);
    const rendered = renderer.renderer.rules.link_open(
        [token],
        0,
        {},
        {},
        {
            renderToken(tokens, idx) {
                return `<a ${tokens[idx].attrs.map(([name, value]) => `${name}="${value}"`).join(' ')}>`;
            },
        },
    );

    assert.equal(
        rendered,
        '<a href="https://example.com" target="_blank" rel="noopener noreferrer">',
    );
});

test('ensureAnchorOpensInNewTab normalizes external anchors', () => {
    const anchor = createFakeAnchor({
        href: 'https://example.com',
        rel: 'nofollow',
        target: '_self',
    });

    ensureAnchorOpensInNewTab(anchor);

    assert.deepEqual(anchor.snapshot(), {
        href: 'https://example.com',
        rel: 'nofollow noopener noreferrer',
        target: '_blank',
    });
});

test('ensureAnchorOpensInNewTab leaves hash anchors alone', () => {
    const anchor = createFakeAnchor({
        href: '#note-123',
        rel: 'nofollow',
    });

    ensureAnchorOpensInNewTab(anchor);

    assert.deepEqual(anchor.snapshot(), {
        href: '#note-123',
        rel: 'nofollow',
    });
});

test('ensureAnchorsOpenInNewTabs updates every external anchor in a root element', () => {
    const externalAnchor = createFakeAnchor({ href: 'https://example.com' });
    const relativeAnchor = createFakeAnchor({ href: '/docs' });
    const hashAnchor = createFakeAnchor({ href: '#note-123' });
    const rootElement = {
        querySelectorAll(selector) {
            assert.equal(selector, 'a[href]');
            return [externalAnchor, relativeAnchor, hashAnchor];
        },
    };

    ensureAnchorsOpenInNewTabs(rootElement);

    assert.deepEqual(externalAnchor.snapshot(), {
        href: 'https://example.com',
        rel: 'noopener noreferrer',
        target: '_blank',
    });
    assert.deepEqual(relativeAnchor.snapshot(), {
        href: '/docs',
        rel: 'noopener noreferrer',
        target: '_blank',
    });
    assert.deepEqual(hashAnchor.snapshot(), {
        href: '#note-123',
    });
});
