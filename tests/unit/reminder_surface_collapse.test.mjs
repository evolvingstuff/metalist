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
        this.style = {};
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
        if (name === 'data-reminder-surface-open-registry') {
            this.dataset.reminderSurfaceOpenRegistry = String(value);
        }
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    removeAttribute(name) {
        this.attributes.delete(name);
    }

    getBoundingClientRect() {
        return {
            top: 0,
            right: 320,
            bottom: 48,
            left: 0,
            width: 320,
            height: 48,
        };
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
        if (selector === '[data-reminder-surface-open-registry]') {
            return this.dataset.reminderSurfaceOpenRegistry === 'true';
        }
        return false;
    }
}

function installReminderSurfaceDom(t, options = {}) {
    if (!options || typeof options !== 'object') {
        throw new Error('installReminderSurfaceDom options must be object');
    }
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalHTMLElement = globalThis.HTMLElement;
    const originalSessionStorage = globalThis.sessionStorage;
    const originalFetch = globalThis.fetch;
    const originalCustomEvent = globalThis.CustomEvent;
    const elementsById = new Map();
    const documentListeners = new Map();
    const body = new FakeElement('body');
    const preferences = { ...(options.preferences ?? {}) };
    const reminders = Array.isArray(options.reminders) ? options.reminders : [];
    const preferenceWrites = [];

    globalThis.HTMLElement = FakeElement;
    globalThis.sessionStorage = {
        getItem(key) {
            if (key === 'metalist_tab_id') {
                return 'test-tab';
            }
            return null;
        },
        setItem() {},
    };
    globalThis.window = {
        setTimeout(callback, delay) {
            if (typeof callback === 'function' && delay === 240) {
                callback();
            }
            return 1;
        },
        clearTimeout() {},
        setInterval() {
            return 1;
        },
        clearInterval() {},
        requestAnimationFrame(callback) {
            if (typeof callback !== 'function') {
                throw new Error('requestAnimationFrame requires callback');
            }
            callback();
            return 1;
        },
        cancelAnimationFrame() {},
    };
    globalThis.CustomEvent = class CustomEvent {
        constructor(type, init = {}) {
            this.type = type;
            this.detail = init.detail;
        }
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
        addEventListener(type, listener) {
            if (typeof type !== 'string' || typeof listener !== 'function') {
                throw new Error('document.addEventListener requires type and listener');
            }
            const listeners = documentListeners.get(type) ?? new Set();
            listeners.add(listener);
            documentListeners.set(type, listeners);
        },
        removeEventListener(type, listener) {
            const listeners = documentListeners.get(type);
            if (listeners === undefined) {
                return;
            }
            listeners.delete(listener);
        },
        dispatchEvent(event) {
            if (!event || typeof event.type !== 'string') {
                throw new Error('document.dispatchEvent requires event type');
            }
            const listeners = documentListeners.get(event.type) ?? new Set();
            for (const listener of listeners) {
                listener(event);
            }
            return true;
        },
    };
    globalThis.fetch = async (url, requestOptions = {}) => {
        if (url === '/api2/auth/client-state') {
            return Response.json({
                preferences,
                command_palette_usage: {},
            });
        }
        if (url === '/api2/auth/client-state/preferences') {
            const bodyPayload = JSON.parse(requestOptions.body);
            Object.keys(preferences).forEach((key) => {
                delete preferences[key];
            });
            Object.assign(preferences, bodyPayload.preferences);
            preferenceWrites.push({ ...preferences });
            return Response.json({ preferences });
        }
        if (url === '/api2/reminders') {
            return Response.json({
                reminders,
                missed: [],
            });
        }
        throw new Error(`Unexpected fetch URL: ${url}`);
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
        if (typeof originalFetch === 'undefined') {
            delete globalThis.fetch;
        } else {
            globalThis.fetch = originalFetch;
        }
        if (typeof originalCustomEvent === 'undefined') {
            delete globalThis.CustomEvent;
        } else {
            globalThis.CustomEvent = originalCustomEvent;
        }
    });

    return { body, preferences, preferenceWrites };
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

function reminderMirrorEntry(id) {
    return {
        id,
        title: `Reminder ${id}`,
        details: '',
        status: 'active',
        time_mode: 'date_only',
        next_fire_date: '2000-01-01',
        pre_reminder: null,
    };
}

test('reminder surface toggle collapses and new reminders auto-expand the stack', async (t) => {
    const { preferences, preferenceWrites } = installReminderSurfaceDom(t);
    const { ReminderSurface } = await import('../../app/static/js/modules/reminder-surface-service.js');

    ReminderSurface._renderEvent(reminderEvent('r1'));

    const container = document.getElementById('reminder-surface');
    assert.ok(container instanceof HTMLElement);
    assert.equal(container.querySelectorAll('.reminder-surface-item').length, 1);

    let toggle = container.querySelector('[data-reminder-surface-toggle]');
    assert.ok(toggle instanceof HTMLElement);
    assert.equal(toggle.getAttribute('aria-expanded'), 'true');
    assert.equal(container.classList.contains('is-collapsed'), false);

    await ReminderSurface._setExpanded(false);

    assert.equal(container.classList.contains('is-collapsed'), true);
    assert.equal(toggle.getAttribute('aria-expanded'), 'false');
    assert.match(toggle.innerHTML, /↓/);
    assert.equal(preferences['pref.reminder_surface_expanded'], 'false');

    ReminderSurface._renderEvent(reminderEvent('r2'));
    await new Promise((resolve) => {
        setTimeout(resolve, 0);
    });

    toggle = container.querySelector('[data-reminder-surface-toggle]');
    assert.equal(container.querySelectorAll('.reminder-surface-item').length, 2);
    assert.equal(container.classList.contains('is-collapsed'), false);
    assert.equal(toggle.getAttribute('aria-expanded'), 'true');
    assert.match(toggle.innerHTML, /↑/);
    assert.equal(preferences['pref.reminder_surface_expanded'], 'true');
    assert.equal(preferenceWrites.length, 2);
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

test('reminder surface title requests reminders modal filtered to title', async (t) => {
    installReminderSurfaceDom(t);
    const { ReminderSurface } = await import('../../app/static/js/modules/reminder-surface-service.js');

    ReminderSurface._renderEvent(reminderEvent('filtered-title'));

    const container = document.getElementById('reminder-surface');
    const item = container.querySelector('.reminder-surface-item');
    assert.ok(item instanceof HTMLElement);
    assert.equal(item.dataset.reminderTitle, 'Reminder filtered-title');

    const titleButton = new HTMLElement('button');
    titleButton.setAttribute('data-reminder-surface-open-registry', 'true');
    item.appendChild(titleButton);

    const requests = [];
    document.addEventListener('metalist:open-reminders', (event) => {
        requests.push(event.detail);
    });

    await ReminderSurface._handleSurfaceClick({ target: titleButton });

    assert.deepEqual(requests, [{ search: 'Reminder filtered-title' }]);
});

test('reminder surface loads collapsed preference from database-backed client state', async (t) => {
    installReminderSurfaceDom(t, {
        preferences: {
            'pref.reminder_surface_expanded': 'false',
        },
        reminders: [reminderMirrorEntry('r4')],
    });
    const { ReminderSurface } = await import('../../app/static/js/modules/reminder-surface-service.js');

    ReminderSurface.stop();
    await ReminderSurface.start();

    const container = document.getElementById('reminder-surface');
    const toggle = container.querySelector('[data-reminder-surface-toggle]');

    assert.ok(toggle instanceof HTMLElement);
    assert.equal(container.classList.contains('is-collapsed'), true);
    assert.equal(toggle.getAttribute('aria-expanded'), 'false');
});
