import assert from 'node:assert/strict';
import test from 'node:test';

function installBrowserEnvironment(t) {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalHTMLElement = globalThis.HTMLElement;
    const originalHTMLImageElement = globalThis.HTMLImageElement;
    const originalSessionStorage = globalThis.sessionStorage;
    const originalLocalStorage = globalThis.localStorage;

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

    class FakeClassList {
        constructor(initialClasses = []) {
            this.classes = new Set(initialClasses);
        }

        add(...classNames) {
            for (const className of classNames) {
                this.classes.add(className);
            }
        }

        remove(...classNames) {
            for (const className of classNames) {
                this.classes.delete(className);
            }
        }

        contains(className) {
            return this.classes.has(className);
        }

        toggle(className, force) {
            const shouldHaveClass = typeof force === 'boolean' ? force : !this.classes.has(className);
            if (shouldHaveClass) {
                this.classes.add(className);
            } else {
                this.classes.delete(className);
            }
            return shouldHaveClass;
        }
    }

    class FakeElement {
        constructor(tagName) {
            this.tagName = tagName.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = {};
            this.classList = new FakeClassList();
            this.parentElement = null;
            this.isConnected = false;
            this.contentEditable = 'false';
            this.textContent = '';
            this.type = '';
            this._innerHTML = '';
        }

        get firstChild() {
            return this.children.length > 0 ? this.children[0] : null;
        }

        get innerHTML() {
            return this._innerHTML;
        }

        set innerHTML(value) {
            this._innerHTML = String(value);
        }

        appendChild(child) {
            child.parentElement = this;
            child.isConnected = this.isConnected;
            this.children.push(child);
            return child;
        }

        insertBefore(child, reference) {
            if (child.parentElement) {
                child.remove();
            }
            child.parentElement = this;
            child.isConnected = this.isConnected;
            if (reference === null || typeof reference === 'undefined') {
                this.children.push(child);
                return child;
            }
            const index = this.children.indexOf(reference);
            if (index === -1) {
                throw new Error('insertBefore reference is not a child');
            }
            this.children.splice(index, 0, child);
            return child;
        }

        remove() {
            if (!this.parentElement) {
                return;
            }
            const siblings = this.parentElement.children;
            const index = siblings.indexOf(this);
            if (index !== -1) {
                siblings.splice(index, 1);
            }
            this.parentElement = null;
            this.isConnected = false;
        }

        setAttribute(name, value) {
            this.attributes[name] = String(value);
        }

        getAttribute(name) {
            return Object.prototype.hasOwnProperty.call(this.attributes, name)
                ? this.attributes[name]
                : null;
        }

        removeAttribute(name) {
            delete this.attributes[name];
        }

        querySelector(selector) {
            if (selector === ':scope > .note-content') {
                return this.children.find((child) => child.classList.contains('note-content')) || null;
            }
            if (selector === ':scope > .note-collapse-toggle') {
                return this.children.find((child) => child.classList.contains('note-collapse-toggle')) || null;
            }
            if (selector === ':scope > .note-children') {
                return this.children.find((child) => child.classList.contains('note-children')) || null;
            }
            return null;
        }

        querySelectorAll(selector) {
            if (selector === 'a[href]' || selector === '.note-file-image-embed[data-file-ref-id]') {
                return [];
            }
            if (selector === '[data-note-id]') {
                const matches = [];
                const visit = (node) => {
                    for (const child of node.children) {
                        if (child.dataset && typeof child.dataset.noteId === 'string') {
                            matches.push(child);
                        }
                        visit(child);
                    }
                };
                visit(this);
                return matches;
            }
            return [];
        }

        getBoundingClientRect() {
            return { height: 20 };
        }

        get scrollHeight() {
            return 20;
        }
    }

    class FakeImageElement extends FakeElement {}

    const elementByNoteId = new Map();
    const notesContainer = new FakeElement('div');
    notesContainer.isConnected = true;

    const document = {
        createElement(tagName) {
            return tagName.toLowerCase() === 'img'
                ? new FakeImageElement(tagName)
                : new FakeElement(tagName);
        },
        createRange() {
            return {
                selectNodeContents() {},
                getClientRects() {
                    return [{ top: 0, width: 100, height: 20 }];
                },
                detach() {},
            };
        },
        getElementById(id) {
            return id === 'notes-container' ? notesContainer : null;
        },
        querySelector(selector) {
            const match = selector.match(/^\[data-note-id="([^"]+)"\]$/);
            if (!match) {
                return null;
            }
            return elementByNoteId.get(match[1]) || null;
        },
        querySelectorAll() {
            return [];
        },
    };

    globalThis.HTMLElement = FakeElement;
    globalThis.HTMLImageElement = FakeImageElement;
    globalThis.document = document;
    globalThis.window = {
        addEventListener() {},
        getComputedStyle() {
            return { lineHeight: '20px', fontSize: '16px' };
        },
    };
    globalThis.sessionStorage = createStorage();
    globalThis.localStorage = createStorage();

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.HTMLImageElement = originalHTMLImageElement;
        globalThis.sessionStorage = originalSessionStorage;
        globalThis.localStorage = originalLocalStorage;
    });

    return {
        createElement: (tagName) => document.createElement(tagName),
        elementByNoteId,
        notesContainer,
    };
}

test('diff refresh preserves current editor content after edit-session changes', async (t) => {
    const env = installBrowserEnvironment(t);
    const { ModeContextInstance: ModeContext } = await import(
        '../../app/static/js/modules/mode-manager/mode-context.js'
    );
    const { applyDifferentialView } = await import(
        '../../app/static/js/modules/mode-manager/services/differential-view-service.js'
    );

    ModeContext._editing = true;
    ModeContext._dirty = false;
    ModeContext._currentNoteId = 'parent-note';
    ModeContext._editSessionHasEdits = true;

    const noteElement = env.createElement('div');
    noteElement.classList.add('note', 'editing', 'interactive');
    noteElement.dataset.noteId = 'parent-note';
    noteElement.dataset.parentId = '';
    noteElement.dataset.contentHash = 'hash-before-child-toggle';
    noteElement.dataset.snapshotHash = 'hash-before-child-toggle';
    noteElement.dataset.lockOwner = 'client-1';
    noteElement.dataset.isCollapsed = 'false';
    noteElement.dataset.hasChildren = 'true';
    noteElement.dataset.isCollapsible = 'true';
    noteElement.dataset.noteTags = '';
    noteElement.dataset.searchRedacted = 'false';

    const collapseToggle = env.createElement('button');
    collapseToggle.classList.add('note-collapse-toggle');
    noteElement.appendChild(collapseToggle);

    const contentElement = env.createElement('div');
    contentElement.classList.add('note-content');
    contentElement.innerHTML = 'server content plus typed edit';
    noteElement.appendChild(contentElement);

    const tagsElement = env.createElement('div');
    tagsElement.classList.add('note-tags');
    noteElement.appendChild(tagsElement);

    env.notesContainer.appendChild(noteElement);
    env.elementByNoteId.set('parent-note', noteElement);

    const result = applyDifferentialView({
        currentClientId: 'client-1',
        editingNoteId: 'parent-note',
        diffOps: [],
        locks: {
            'parent-note': 'client-1',
        },
        lockDiffs: {},
        notes: {
            'parent-note': {
                content: 'server content',
                hash: 'hash-after-child-toggle',
                tags: '',
                flags: {
                    isEditing: true,
                    isCollapsed: false,
                    hasChildren: true,
                    isCollapsible: true,
                },
            },
        },
    }, {});

    assert.equal(contentElement.innerHTML, 'server content plus typed edit');
    assert.equal(result.vdomOperations, 0);
    assert.equal(noteElement.dataset.snapshotHash, 'hash-after-child-toggle');
    assert.equal(noteElement.dataset.contentHash, 'hash-before-child-toggle');
});
