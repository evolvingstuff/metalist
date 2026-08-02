import assert from 'node:assert/strict';
import test from 'node:test';

function installImageContextDom(t) {
    const originalHTMLElement = globalThis.HTMLElement;
    const originalHTMLImageElement = globalThis.HTMLImageElement;
    const originalSessionStorage = globalThis.sessionStorage;
    const originalLocalStorage = globalThis.localStorage;
    const originalWindow = globalThis.window;

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

    class FakeHTMLElement {
        constructor(dataset = {}) {
            this.dataset = dataset;
        }

        closest() {
            return null;
        }
    }

    class FakeImageElement extends FakeHTMLElement {
        constructor(options) {
            super(options.dataset);
            this.currentSrc = options.currentSrc;
            this.src = options.src;
            this.dataset = options.dataset;
            this.alt = options.alt;
            this.closestBySelector = options.closestBySelector;
        }

        closest(selector) {
            if (selector === 'img') {
                return this;
            }
            return this.closestBySelector[selector] ?? null;
        }
    }

    globalThis.HTMLElement = FakeHTMLElement;
    globalThis.HTMLImageElement = FakeImageElement;
    globalThis.sessionStorage = createStorage();
    globalThis.localStorage = createStorage();
    globalThis.window = {
        open() {
            return null;
        },
    };

    t.after(() => {
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.HTMLImageElement = originalHTMLImageElement;
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.localStorage = originalLocalStorage;
        globalThis.window = originalWindow;
    });

    return { FakeHTMLElement, FakeImageElement };
}

test('resolveImageContextFromElement returns inline image context', async (t) => {
    const { FakeHTMLElement, FakeImageElement } = installImageContextDom(t);
    const { resolveImageContextFromElement } = await import(
        '../../app/static/js/modules/mode-manager/services/image-context-menu-action-service.js'
    );
    const image = new FakeImageElement({
        currentSrc: 'data:image/png;base64,AAAA',
        src: 'data:image/png;base64,AAAA',
        dataset: { inlineImageOccurrence: '2' },
        alt: 'Inline diagram',
        closestBySelector: {
            '.note[data-note-id]': new FakeHTMLElement({ noteId: 'note-123' }),
        },
    });

    assert.deepEqual(resolveImageContextFromElement(image), {
        sourceKind: 'inline',
        fileId: null,
        hostNoteId: 'note-123',
        occurrenceIndex: 2,
        src: 'data:image/png;base64,AAAA',
        alt: 'Inline diagram',
        filename: null,
    });
});

test('resolveImageContextFromElement returns file image context', async (t) => {
    const { FakeHTMLElement, FakeImageElement } = installImageContextDom(t);
    const { resolveImageContextFromElement } = await import(
        '../../app/static/js/modules/mode-manager/services/image-context-menu-action-service.js'
    );
    const image = new FakeImageElement({
        currentSrc: 'blob:preview-1',
        src: 'blob:preview-1',
        dataset: { fileRefId: 'file-123' },
        alt: 'Saved photo',
        closestBySelector: {
            '.note-reference-block[data-ref-occurrence]': new FakeHTMLElement({
                refHostNoteId: 'note-456',
                refOccurrence: '3',
            }),
        },
    });

    assert.deepEqual(resolveImageContextFromElement(image), {
        sourceKind: 'file',
        fileId: 'file-123',
        hostNoteId: 'note-456',
        occurrenceIndex: 3,
        src: 'blob:preview-1',
        alt: 'Saved photo',
        filename: null,
    });
});

test('buildSuggestedImageFilename uses sanitized alt and MIME extension', async (t) => {
    installImageContextDom(t);
    const { buildSuggestedImageFilename } = await import(
        '../../app/static/js/modules/mode-manager/services/image-context-menu-action-service.js'
    );
    const filename = buildSuggestedImageFilename(
        {
            sourceKind: 'inline',
            fileId: null,
            src: 'data:image/jpeg;base64,AAAA',
            alt: 'Trip photo 01!',
            filename: null,
        },
        'image/jpeg',
    );

    assert.equal(filename, 'Trip-photo-01.jpg');
});

test('openImageInNewTabFromContext does not fail when noopener returns null', async (t) => {
    installImageContextDom(t);
    let openedUrl = null;
    globalThis.window.open = (url, target, features) => {
        assert.equal(target, '_blank');
        assert.equal(features, 'noopener');
        openedUrl = url;
        return null;
    };
    const { openImageInNewTabFromContext } = await import(
        '../../app/static/js/modules/mode-manager/services/image-context-menu-action-service.js'
    );

    await openImageInNewTabFromContext({
        sourceKind: 'inline',
        fileId: null,
        src: 'data:image/png;base64,AAAA',
        alt: '',
        filename: null,
    });

    assert.equal(openedUrl, 'data:image/png;base64,AAAA');
});
