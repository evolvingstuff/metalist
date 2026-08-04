import assert from 'node:assert/strict';
import test from 'node:test';

import {
    hideContextMenu,
    showContextMenu,
} from '../../app/static/js/modules/context-menu/context-menu-service.js';


class FakeClassList {
    constructor() {
        this.values = new Set();
    }

    add(...classNames) {
        classNames.forEach((className) => this.values.add(className));
    }

    remove(...classNames) {
        classNames.forEach((className) => this.values.delete(className));
    }

    contains(className) {
        return this.values.has(className);
    }
}


class FakeElement {
    constructor(tagName, ownerDocument) {
        this.tagName = tagName.toUpperCase();
        this.ownerDocument = ownerDocument;
        this.id = '';
        this.classList = new FakeClassList();
        this._className = '';
        this.style = {};
        this.dataset = {};
        this.children = [];
        this.parentElement = null;
        this.attributes = new Map();
        this.listeners = new Map();
        this.disabled = false;
        this.focusCount = 0;
        this.textContent = '';
    }

    set className(value) {
        this._className = value;
        this.classList = new FakeClassList();
        value.split(/\s+/).filter(Boolean).forEach((className) => this.classList.add(className));
    }

    get className() {
        return this._className;
    }

    set innerHTML(value) {
        assert.equal(value, '');
        this.children = [];
    }

    appendChild(child) {
        child.parentElement = this;
        this.children.push(child);
        return child;
    }

    setAttribute(name, value) {
        this.attributes.set(name, value);
    }

    addEventListener(type, listener) {
        this.listeners.set(type, listener);
    }

    dispatch(type) {
        const listener = this.listeners.get(type);
        assert.equal(typeof listener, 'function');
        listener({ target: this });
    }

    contains(candidate) {
        if (candidate === this) {
            return true;
        }
        return this.children.some((child) => child.contains(candidate));
    }

    querySelector(selector) {
        assert.equal(selector, '.context-menu-item:not(:disabled)');
        return this.children.find((child) => (
            child.classList.contains('context-menu-item') && !child.disabled
        )) ?? null;
    }

    getBoundingClientRect() {
        if (this.classList.contains('context-menu-item')) {
            return { left: 100, right: 300, top: 100, width: 200, height: 32 };
        }
        return { left: 100, right: 300, top: 100, width: 200, height: 240 };
    }

    focus() {
        this.focusCount += 1;
        this.ownerDocument.activeElement = this;
    }
}


class FakeButtonElement extends FakeElement {
    constructor(ownerDocument) {
        super('button', ownerDocument);
        this.type = 'button';
    }
}


function installFakeDom() {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalElement = globalThis.Element;
    const originalHtmlButtonElement = globalThis.HTMLButtonElement;

    const fakeDocument = {
        activeElement: null,
        listeners: new Map(),
        addEventListener(type, listener) {
            this.listeners.set(type, listener);
        },
        createElement(tagName) {
            if (tagName === 'button') {
                return new FakeButtonElement(this);
            }
            return new FakeElement(tagName, this);
        },
        createElementNS(_namespace, tagName) {
            return new FakeElement(tagName, this);
        },
    };
    fakeDocument.body = new FakeElement('body', fakeDocument);

    globalThis.document = fakeDocument;
    globalThis.window = {
        innerWidth: 1200,
        innerHeight: 800,
        addEventListener() {},
    };
    globalThis.Element = FakeElement;
    globalThis.HTMLButtonElement = FakeButtonElement;

    return {
        fakeDocument,
        restore() {
            globalThis.document = originalDocument;
            globalThis.window = originalWindow;
            globalThis.Element = originalElement;
            globalThis.HTMLButtonElement = originalHtmlButtonElement;
        },
    };
}


test('pointer hover opens a submenu without stealing focus into the flyout', () => {
    const dom = installFakeDom();
    try {
        showContextMenu({
            items: [{
                id: 'add-style',
                label: 'Add Style',
                enabled: true,
                submenu: [{
                    id: 'add-style-highlighter',
                    label: 'Highlighter',
                    enabled: true,
                    onSelect() {},
                }],
            }],
            position: { x: 100, y: 100 },
        });

        const rootMenu = dom.fakeDocument.body.children.find(
            (element) => element.id === 'context-menu',
        );
        assert.ok(rootMenu);
        assert.equal(rootMenu.children.length, 1);

        rootMenu.children[0].dispatch('mouseenter');

        const submenu = dom.fakeDocument.body.children.find(
            (element) => element.id === 'context-submenu',
        );
        assert.ok(submenu);
        assert.equal(submenu.style.display, 'block');
        assert.equal(submenu.children.length, 1);
        assert.equal(submenu.children[0].focusCount, 0);
        assert.equal(dom.fakeDocument.activeElement, null);

        rootMenu.children[0].dispatch('focus');

        assert.equal(submenu.children.length, 1);
        assert.equal(submenu.children[0].focusCount, 1);
        assert.equal(dom.fakeDocument.activeElement, submenu.children[0]);
    } finally {
        hideContextMenu();
        dom.restore();
    }
});
