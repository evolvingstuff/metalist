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

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.listeners = {};
        this.style = {};
        this.id = '';
        this.className = '';
        this.textContent = '';
    }

    appendChild(child) {
        this.children.push(child);
        return child;
    }

    addEventListener(type, listener) {
        this.listeners[type] = listener;
    }

    removeEventListener(type, listener) {
        if (this.listeners[type] === listener) {
            delete this.listeners[type];
        }
    }

    querySelector(selector) {
        if (selector === '#image-file-insert-choice-description') {
            return this.descriptionElement;
        }
        if (selector === '#image-file-insert-choice-embed') {
            return this.embedButton;
        }
        if (selector === '#image-file-insert-choice-attach') {
            return this.attachButton;
        }
        if (selector === '#image-file-insert-choice-cancel') {
            return this.cancelButton;
        }
        if (selector === '.modal-close-button') {
            return this.closeButton;
        }
        return null;
    }

    set innerHTML(value) {
        this._innerHTML = value;
        this.descriptionElement = new FakeElement('p');
        this.descriptionElement.id = 'image-file-insert-choice-description';
        this.embedButton = new FakeButton('button');
        this.embedButton.id = 'image-file-insert-choice-embed';
        this.attachButton = new FakeButton('button');
        this.attachButton.id = 'image-file-insert-choice-attach';
        this.cancelButton = new FakeButton('button');
        this.cancelButton.id = 'image-file-insert-choice-cancel';
        this.closeButton = new FakeButton('button');
        this.closeButton.className = 'modal-close-button';
    }

    get innerHTML() {
        return this._innerHTML;
    }
}

class FakeButton extends FakeElement {
    focus() {
        this.focused = true;
    }

    closest(selector) {
        if (selector === `#${this.id}`) {
            return this;
        }
        if (selector === '.modal-close-button' && this.className === 'modal-close-button') {
            return this;
        }
        return null;
    }
}

function installDom(t) {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalSessionStorage = globalThis.sessionStorage;
    const originalHTMLElement = globalThis.HTMLElement;
    const originalHTMLButtonElement = globalThis.HTMLButtonElement;

    let modalElement = null;
    const documentListeners = {};
    globalThis.HTMLElement = FakeElement;
    globalThis.HTMLButtonElement = FakeButton;
    globalThis.sessionStorage = createStorage();
    globalThis.window = {
        setTimeout(callback) {
            callback();
            return 1;
        },
    };
    globalThis.document = {
        body: {
            appendChild(element) {
                modalElement = element;
                return element;
            },
        },
        getElementById(id) {
            if (id === 'image-file-insert-choice-modal') {
                return modalElement;
            }
            return null;
        },
        createElement(tagName) {
            return new FakeElement(tagName);
        },
        addEventListener(type, listener) {
            documentListeners[type] = listener;
        },
        removeEventListener(type, listener) {
            if (documentListeners[type] === listener) {
                delete documentListeners[type];
            }
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.HTMLButtonElement = originalHTMLButtonElement;
    });

    return {
        get modalElement() {
            return modalElement;
        },
    };
}

test('image file choice modal opens and resolves after the strict modal stack refactor', async (t) => {
    const dom = installDom(t);
    const [{ promptForImageFileInsertMode }, { ModeContextInstance: ModeContext }] = await Promise.all([
        import('../../app/static/js/modules/mode-manager/services/image-file-insert-choice-modal-service.js'),
        import('../../app/static/js/modules/mode-manager/mode-context.js'),
    ]);

    const choicePromise = promptForImageFileInsertMode({ imageCount: 1, source: 'drop' });

    assert.equal(ModeContext.topModal, 'imageFileInsertChoiceModal');
    assert.equal(dom.modalElement.style.display, 'block');

    dom.modalElement.listeners.click({
        target: dom.modalElement.attachButton,
    });

    assert.equal(await choicePromise, 'attach');
    assert.equal(ModeContext.topModal, null);
    assert.equal(dom.modalElement.style.display, 'none');
});


test('image file choice modal resolves as cancelled from the standard close button', async (t) => {
    const dom = installDom(t);
    const [{ promptForImageFileInsertMode }, { ModeContextInstance: ModeContext }] = await Promise.all([
        import('../../app/static/js/modules/mode-manager/services/image-file-insert-choice-modal-service.js'),
        import('../../app/static/js/modules/mode-manager/mode-context.js'),
    ]);

    const choicePromise = promptForImageFileInsertMode({ imageCount: 2, source: 'paste' });
    dom.modalElement.listeners.click({ target: dom.modalElement.closeButton });

    assert.equal(await choicePromise, null);
    assert.equal(ModeContext.topModal, null);
    assert.equal(dom.modalElement.style.display, 'none');
});
