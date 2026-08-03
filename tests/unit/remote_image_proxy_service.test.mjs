import assert from 'node:assert/strict';
import test from 'node:test';

function installTestDom(t) {
    const originalWindow = globalThis.window;
    const originalDocument = globalThis.document;
    const originalUrl = globalThis.URL;
    const originalHTMLElement = globalThis.HTMLElement;
    const originalHtmlImageElement = globalThis.HTMLImageElement;
    const originalSessionStorage = globalThis.sessionStorage;
    const originalFetch = globalThis.fetch;

    class FakeElement {
        constructor() {
            this.children = [];
            this.dataset = {};
        }

        appendChild(child) {
            this.children.push(child);
            return child;
        }

        querySelectorAll(selector) {
            if (!new Set([
                'img[data-remote-image-proxy-src]',
                'img[data-remote-image-source-url]',
                'img[src]',
            ]).has(selector)) {
                throw new Error(`Unsupported selector: ${selector}`);
            }
            const matches = [];
            for (const child of this.children) {
                const matchesProxy = selector === 'img[data-remote-image-proxy-src]'
                    && typeof child.dataset.remoteImageProxySrc === 'string';
                const matchesSourceData = selector === 'img[data-remote-image-source-url]'
                    && typeof child.dataset.remoteImageSourceUrl === 'string';
                const matchesSourceAttribute = selector === 'img[src]'
                    && child.getAttribute('src') !== null;
                if (child instanceof FakeImageElement && (
                    matchesProxy
                    || matchesSourceData
                    || matchesSourceAttribute
                )) {
                    matches.push(child);
                }
                matches.push(...child.querySelectorAll(selector));
            }
            return matches;
        }
    }

    class FakeImageElement extends FakeElement {
        constructor(proxyPath) {
            super();
            this.attributes = new Map();
            if (typeof proxyPath === 'string') {
                this.dataset.remoteImageProxySrc = proxyPath;
            }
            this.src = '';
        }

        getAttribute(name) {
            return this.attributes.has(name) ? this.attributes.get(name) : null;
        }

        setAttribute(name, value) {
            this.attributes.set(name, value);
            if (name === 'src') {
                this.src = value;
            }
        }

        removeAttribute(name) {
            this.attributes.delete(name);
            if (name === 'src') {
                this.src = '';
            }
        }
    }

    const documentRoot = new FakeElement();
    const sessionEntries = new Map([['metalist_tab_id', 'tab-123']]);
    globalThis.HTMLElement = FakeElement;
    globalThis.HTMLImageElement = FakeImageElement;
    globalThis.document = documentRoot;
    globalThis.window = { addEventListener() {} };
    globalThis.sessionStorage = {
        getItem(key) {
            return sessionEntries.has(key) ? sessionEntries.get(key) : null;
        },
    };
    globalThis.URL = {
        createObjectURL() {
            return 'blob:remote-image';
        },
        revokeObjectURL() {},
    };

    t.after(() => {
        globalThis.window = originalWindow;
        globalThis.document = originalDocument;
        globalThis.URL = originalUrl;
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.HTMLImageElement = originalHtmlImageElement;
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.fetch = originalFetch;
    });

    return { FakeElement, FakeImageElement, documentRoot };
}

async function flushAsyncWork() {
    await Promise.resolve();
    await Promise.resolve();
    await new Promise((resolve) => {
        setTimeout(resolve, 0);
    });
}

test('remote image hydration uses tab-bound same-origin fetch and an in-memory blob URL', async (t) => {
    const { FakeElement, FakeImageElement, documentRoot } = installTestDom(t);
    const proxyPath = '/api2/remote-images/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
    const notesContainer = new FakeElement();
    const firstImage = new FakeImageElement(proxyPath);
    const secondImage = new FakeImageElement(proxyPath);
    notesContainer.appendChild(firstImage);
    notesContainer.appendChild(secondImage);
    documentRoot.appendChild(notesContainer);

    const requests = [];
    globalThis.fetch = async (url, options) => {
        requests.push({ url, options });
        return {
            ok: true,
            async blob() {
                return new Blob([Buffer.from('image')], { type: 'image/png' });
            },
        };
    };

    const { hydrateRemoteImageProxies } = await import(
        '../../app/static/js/modules/mode-manager/services/remote-image-proxy-service.js'
    );
    hydrateRemoteImageProxies(notesContainer);
    await flushAsyncWork();

    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, proxyPath);
    assert.equal(requests[0].options.credentials, 'same-origin');
    assert.equal(requests[0].options.cache, 'no-store');
    assert.equal(requests[0].options.headers['X-Metalist-Tab-Id'], 'tab-123');
    assert.equal(firstImage.src, 'blob:remote-image');
    assert.equal(secondImage.src, 'blob:remote-image');
    assert.equal(firstImage.dataset.remoteImageProxyState, 'loaded');
    assert.equal(secondImage.dataset.remoteImageProxyState, 'loaded');
});

test('remote editor image registration proxies display but restores original URL for storage', async (t) => {
    const { FakeElement, FakeImageElement } = installTestDom(t);
    const editorRoot = new FakeElement();
    const image = new FakeImageElement(null);
    image.setAttribute('src', 'https://images.example/cat.png');
    editorRoot.appendChild(image);

    const requests = [];
    globalThis.fetch = async (url, options) => {
        requests.push({ url, options });
        return {
            ok: true,
            async json() {
                return {
                    images: [{
                        source_url: 'https://images.example/cat.png',
                        proxy_path: '/api2/remote-images/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
                    }],
                };
            },
        };
    };

    const {
        prepareRemoteImageElementsForEditing,
        restoreRemoteImageElementsForStorage,
    } = await import(
        '../../app/static/js/modules/mode-manager/services/remote-image-proxy-service.js'
    );
    const prepared = await prepareRemoteImageElementsForEditing(editorRoot);

    assert.equal(prepared, true);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, '/api2/remote-images/registrations');
    assert.equal(requests[0].options.method, 'POST');
    assert.equal(requests[0].options.headers['X-Metalist-Tab-Id'], 'tab-123');
    assert.deepEqual(JSON.parse(requests[0].options.body), {
        source_urls: ['https://images.example/cat.png'],
    });
    assert.equal(image.getAttribute('src'), null);
    assert.equal(image.dataset.remoteImageSourceUrl, 'https://images.example/cat.png');
    assert.equal(
        image.dataset.remoteImageProxySrc,
        '/api2/remote-images/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    );

    restoreRemoteImageElementsForStorage(editorRoot);

    assert.equal(image.getAttribute('src'), 'https://images.example/cat.png');
    assert.equal(image.dataset.remoteImageSourceUrl, undefined);
    assert.equal(image.dataset.remoteImageProxySrc, undefined);
});
