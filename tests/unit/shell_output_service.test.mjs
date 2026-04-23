import assert from 'node:assert/strict';
import test from 'node:test';

function matchesClassSelector(element, selector) {
    if (!(element instanceof globalThis.HTMLElement)) {
        return false;
    }
    const match = /^\.([a-z0-9-]+)$/i.exec(selector);
    if (!match) {
        throw new Error(`Unsupported selector in shell output service test: ${selector}`);
    }
    return element.classList.contains(match[1]);
}

function installShellOutputDom(t) {
    const originalDocument = globalThis.document;
    const originalHTMLElement = globalThis.HTMLElement;
    const originalElement = globalThis.Element;
    const originalHTMLButtonElement = globalThis.HTMLButtonElement;

    class FakeClassList {
        constructor(owner) {
            this._owner = owner;
        }

        add(...classNames) {
            for (const className of classNames) {
                this._owner._classNames.add(className);
            }
        }

        remove(...classNames) {
            for (const className of classNames) {
                this._owner._classNames.delete(className);
            }
        }

        contains(className) {
            return this._owner._classNames.has(className);
        }
    }

    class FakeHTMLElement {
        constructor(tagName) {
            this.tagName = String(tagName).toUpperCase();
            this._classNames = new Set();
            this.classList = new FakeClassList(this);
            this.children = [];
            this.parentNode = null;
            this.dataset = {};
            this.style = {};
            this.hidden = false;
            this.disabled = false;
            this.textContent = '';
            this.type = '';
            this.placeholder = '';
            this.autocomplete = '';
            this.spellcheck = false;
            this.value = '';
            this._listeners = new Map();
            this._attributes = new Map();
        }

        get className() {
            return Array.from(this._classNames).join(' ');
        }

        set className(value) {
            this._classNames = new Set(
                String(value)
                    .split(/\s+/)
                    .map((item) => item.trim())
                    .filter((item) => item !== '')
            );
            this.classList = new FakeClassList(this);
        }

        appendChild(child) {
            if (!(child instanceof FakeHTMLElement)) {
                throw new Error('appendChild expects FakeHTMLElement child');
            }
            child.parentNode = this;
            this.children.push(child);
            return child;
        }

        remove() {
            if (!(this.parentNode instanceof FakeHTMLElement)) {
                return;
            }
            this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
            this.parentNode = null;
        }

        querySelector(selector) {
            const matches = this.querySelectorAll(selector);
            if (matches.length === 0) {
                return null;
            }
            return matches[0];
        }

        querySelectorAll(selector) {
            const matches = [];
            for (const child of this.children) {
                if (matchesClassSelector(child, selector)) {
                    matches.push(child);
                }
                matches.push(...child.querySelectorAll(selector));
            }
            return matches;
        }

        closest(selector) {
            let current = this;
            while (current instanceof FakeHTMLElement) {
                if (matchesClassSelector(current, selector)) {
                    return current;
                }
                current = current.parentNode;
            }
            return null;
        }

        addEventListener(type, handler) {
            if (!this._listeners.has(type)) {
                this._listeners.set(type, []);
            }
            this._listeners.get(type).push(handler);
        }

        dispatchEvent(event) {
            if (typeof event.type !== 'string' || event.type === '') {
                throw new Error('dispatchEvent requires event type');
            }
            event.target = this;
            const listeners = this._listeners.get(event.type);
            if (!Array.isArray(listeners)) {
                return true;
            }
            for (const listener of listeners) {
                listener.call(this, event);
            }
            return true;
        }

        setAttribute(name, value) {
            this._attributes.set(name, String(value));
        }

        getAttribute(name) {
            if (!this._attributes.has(name)) {
                return null;
            }
            return this._attributes.get(name);
        }
    }

    class FakeHTMLButtonElement extends FakeHTMLElement {
        constructor() {
            super('button');
        }
    }

    globalThis.HTMLElement = FakeHTMLElement;
    globalThis.Element = FakeHTMLElement;
    globalThis.HTMLButtonElement = FakeHTMLButtonElement;
    globalThis.document = {
        createElement(tagName) {
            const normalized = String(tagName).toLowerCase();
            if (normalized === 'button') {
                return new FakeHTMLButtonElement();
            }
            return new FakeHTMLElement(tagName);
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.Element = originalElement;
        globalThis.HTMLButtonElement = originalHTMLButtonElement;
    });
}

function createClickEvent() {
    return {
        type: 'click',
        defaultPrevented: false,
        propagationStopped: false,
        preventDefault() {
            this.defaultPrevented = true;
        },
        stopPropagation() {
            this.propagationStopped = true;
        },
    };
}

test('renderShellSnapshot hides the close button while a shell run is active', async (t) => {
    installShellOutputDom(t);
    const {
        SHELL_CLOSE_SELECTOR,
        ensureShellOutputElement,
        ensureShellOutputStructure,
        renderShellSnapshot,
    } = await import('../../app/static/js/modules/mode-manager/services/shell-output-service.js');

    const shellElement = document.createElement('div');
    shellElement.className = 'meta-shell';

    const outputElement = ensureShellOutputElement(shellElement);
    ensureShellOutputStructure(outputElement, 'note-1');
    renderShellSnapshot(outputElement, shellElement, {
        runId: 'run-1',
        status: 'running',
        exitCode: -1,
        stdout: '',
        stderr: '',
        durationMs: 0,
        errorMessage: '',
    });

    const closeButton = outputElement.querySelector(SHELL_CLOSE_SELECTOR);
    assert.ok(closeButton instanceof globalThis.HTMLButtonElement);
    assert.equal(closeButton.hidden, true);
    assert.equal(closeButton.disabled, true);
});

test('ensureShellOutputStructure does not render shell input controls', async (t) => {
    installShellOutputDom(t);
    const {
        ensureShellOutputElement,
        ensureShellOutputStructure,
    } = await import('../../app/static/js/modules/mode-manager/services/shell-output-service.js');

    const shellElement = document.createElement('div');
    shellElement.className = 'meta-shell';

    const outputElement = ensureShellOutputElement(shellElement);
    ensureShellOutputStructure(outputElement, 'note-1');

    assert.equal(outputElement.querySelector('.meta-shell-output-input-row'), null);
    assert.equal(outputElement.querySelector('.meta-shell-output-input'), null);
    assert.equal(outputElement.querySelector('.meta-shell-output-send'), null);
});

test('completed shell feedback can be dismissed from the output header', async (t) => {
    installShellOutputDom(t);
    const {
        SHELL_CLOSE_SELECTOR,
        SHELL_OUTPUT_SELECTOR,
        ensureShellOutputElement,
        ensureShellOutputStructure,
        renderShellSnapshot,
    } = await import('../../app/static/js/modules/mode-manager/services/shell-output-service.js');

    const shellElement = document.createElement('div');
    shellElement.className = 'meta-shell';

    const outputElement = ensureShellOutputElement(shellElement);
    ensureShellOutputStructure(outputElement, 'note-1');
    renderShellSnapshot(outputElement, shellElement, {
        runId: 'run-1',
        status: 'success',
        exitCode: 0,
        stdout: 'done',
        stderr: '',
        durationMs: 1000,
        errorMessage: '',
    });

    const closeButton = outputElement.querySelector(SHELL_CLOSE_SELECTOR);
    assert.ok(closeButton instanceof globalThis.HTMLButtonElement);
    assert.equal(closeButton.hidden, false);
    assert.equal(closeButton.disabled, false);

    const clickEvent = createClickEvent();
    closeButton.dispatchEvent(clickEvent);

    assert.equal(clickEvent.defaultPrevented, true);
    assert.equal(clickEvent.propagationStopped, true);
    assert.equal(shellElement.querySelector(SHELL_OUTPUT_SELECTOR), null);
});
