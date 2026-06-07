import assert from 'node:assert/strict';
import test from 'node:test';

class FakeClassList {
    constructor() {
        this._classes = new Set();
    }

    add(className) {
        this._classes.add(className);
    }

    remove(className) {
        this._classes.delete(className);
    }

    contains(className) {
        return this._classes.has(className);
    }

    toggle(className, force) {
        if (force === true) {
            this.add(className);
            return true;
        }
        if (force === false) {
            this.remove(className);
            return false;
        }
        if (this.contains(className)) {
            this.remove(className);
            return false;
        }
        this.add(className);
        return true;
    }

    setFromString(value) {
        this._classes = new Set(value.split(/\s+/).filter(Boolean));
    }
}

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.parentElement = null;
        this.dataset = {};
        this.attributes = new Map();
        this.classList = new FakeClassList();
        this._className = '';
        this._innerHTML = '';
        this.id = '';
        this.type = '';
    }

    set className(value) {
        this._className = value;
        this.classList.setFromString(value);
    }

    get className() {
        return this._className;
    }

    set innerHTML(value) {
        this._innerHTML = value;
    }

    get innerHTML() {
        return this._innerHTML;
    }

    get lastElementChild() {
        if (this.children.length === 0) {
            return null;
        }
        return this.children[this.children.length - 1];
    }

    appendChild(child) {
        if (!(child instanceof FakeElement)) {
            throw new Error('appendChild requires FakeElement');
        }
        if (child.parentElement !== null) {
            child.remove();
        }
        child.parentElement = this;
        this.children.push(child);
        return child;
    }

    insertBefore(child, reference) {
        if (!(child instanceof FakeElement)) {
            throw new Error('insertBefore requires FakeElement');
        }
        if (!(reference instanceof FakeElement)) {
            throw new Error('insertBefore requires reference FakeElement');
        }
        const index = this.children.indexOf(reference);
        if (index < 0) {
            throw new Error('insertBefore reference missing');
        }
        if (child.parentElement !== null) {
            child.remove();
        }
        child.parentElement = this;
        this.children.splice(index, 0, child);
        return child;
    }

    remove() {
        if (this.parentElement === null) {
            return;
        }
        const siblings = this.parentElement.children;
        const index = siblings.indexOf(this);
        if (index >= 0) {
            siblings.splice(index, 1);
        }
        this.parentElement = null;
    }

    addEventListener() {}

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
        if (name === 'data-reminder-surface-toggle') {
            this.dataset.reminderSurfaceToggle = String(value);
        }
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] ?? null;
    }

    querySelectorAll(selector) {
        const matches = [];
        for (const child of this.children) {
            if (child._matches(selector)) {
                matches.push(child);
            }
            matches.push(...child.querySelectorAll(selector));
        }
        return matches;
    }

    closest(selector) {
        let current = this;
        while (current !== null) {
            if (current._matches(selector)) {
                return current;
            }
            current = current.parentElement;
        }
        return null;
    }

    _matches(selector) {
        if (selector === '.reminder-surface-item') {
            return this.classList.contains('reminder-surface-item');
        }
        if (selector === '[data-reminder-surface-toggle]') {
            return this.dataset.reminderSurfaceToggle === 'true';
        }
        return false;
    }
}

function installReminderSurfaceDom(t) {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalHTMLElement = globalThis.HTMLElement;
    const originalSessionStorage = globalThis.sessionStorage;
    const elementsById = new Map();
    const body = new FakeElement('body');

    globalThis.HTMLElement = FakeElement;
    globalThis.sessionStorage = {
        getItem() {
            return null;
        },
        setItem() {},
    };
    globalThis.window = {
        setTimeout() {
            return 1;
        },
        clearTimeout() {},
        setInterval() {
            return 1;
        },
        clearInterval() {},
    };
    globalThis.document = {
        body,
        visibilityState: 'visible',
        createElement(tagName) {
            return new FakeElement(tagName);
        },
        getElementById(id) {
            return elementsById.get(id) ?? null;
        },
        addEventListener() {},
        removeEventListener() {},
    };
    body.appendChild = (child) => {
        FakeElement.prototype.appendChild.call(body, child);
        if (child.id) {
            elementsById.set(child.id, child);
        }
        return child;
    };

    t.after(() => {
        if (typeof originalDocument === 'undefined') {
            delete globalThis.document;
        } else {
            globalThis.document = originalDocument;
        }
        if (typeof originalWindow === 'undefined') {
            delete globalThis.window;
        } else {
            globalThis.window = originalWindow;
        }
        if (typeof originalHTMLElement === 'undefined') {
            delete globalThis.HTMLElement;
        } else {
            globalThis.HTMLElement = originalHTMLElement;
        }
        if (typeof originalSessionStorage === 'undefined') {
            delete globalThis.sessionStorage;
        } else {
            globalThis.sessionStorage = originalSessionStorage;
        }
    });

    return { body };
}

function reminderEvent(id) {
    return {
        kind: 'due',
        occurrenceKind: 'main',
        occurrenceValue: `2026-06-07:${id}`,
        isDateOnly: true,
        reminder: {
            id,
            title: `Reminder ${id}`,
            details: '',
            time_mode: 'date_only',
        },
    };
}

test('reminder surface toggle collapses and new reminders auto-expand the stack', async (t) => {
    installReminderSurfaceDom(t);
    const { ReminderSurface } = await import('../../app/static/js/modules/reminder-surface-service.js');

    ReminderSurface._renderEvent(reminderEvent('r1'));

    const container = document.getElementById('reminder-surface');
    assert.ok(container instanceof HTMLElement);
    assert.equal(container.querySelectorAll('.reminder-surface-item').length, 1);

    let toggle = container.querySelector('[data-reminder-surface-toggle]');
    assert.ok(toggle instanceof HTMLElement);
    assert.equal(toggle.getAttribute('aria-expanded'), 'true');
    assert.equal(container.classList.contains('is-collapsed'), false);

    ReminderSurface._setExpanded(false);

    assert.equal(container.classList.contains('is-collapsed'), true);
    assert.equal(toggle.getAttribute('aria-expanded'), 'false');
    assert.match(toggle.innerHTML, /↓/);

    ReminderSurface._renderEvent(reminderEvent('r2'));

    toggle = container.querySelector('[data-reminder-surface-toggle]');
    assert.equal(container.querySelectorAll('.reminder-surface-item').length, 2);
    assert.equal(container.classList.contains('is-collapsed'), false);
    assert.equal(toggle.getAttribute('aria-expanded'), 'true');
    assert.match(toggle.innerHTML, /↑/);
});

test('reminder surface toggle disappears when no reminders await acknowledgement', async (t) => {
    installReminderSurfaceDom(t);
    const { ReminderSurface } = await import('../../app/static/js/modules/reminder-surface-service.js');

    ReminderSurface._renderEvent(reminderEvent('r3'));

    const container = document.getElementById('reminder-surface');
    const item = container.querySelector('.reminder-surface-item');
    assert.ok(item instanceof HTMLElement);
    assert.ok(container.querySelector('[data-reminder-surface-toggle]') instanceof HTMLElement);

    ReminderSurface._removeSurfaceItem(item);

    assert.equal(container.querySelector('[data-reminder-surface-toggle]'), null);
    assert.equal(container.classList.contains('is-collapsed'), false);
});
