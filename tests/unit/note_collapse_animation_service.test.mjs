import assert from 'node:assert/strict';
import test from 'node:test';

function installBrowserEnvironment(t, { animatedTransitions }) {
    const originalDocument = globalThis.document;
    const originalWindow = globalThis.window;
    const originalHTMLElement = globalThis.HTMLElement;

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
    }

    class FakeElement {
        constructor(initialClasses = []) {
            this.classList = new FakeClassList(initialClasses);
            this.dataset = {};
            this.style = {};
            this.isConnected = true;
            this.height = 20;
            this.listeners = new Map();
        }

        getBoundingClientRect() {
            return { height: this.height };
        }

        addEventListener(eventName, handler) {
            if (typeof eventName !== 'string' || typeof handler !== 'function') {
                throw new Error('FakeElement.addEventListener requires eventName and handler');
            }
            this.listeners.set(eventName, handler);
        }

        dispatchTransitionEnd(propertyName) {
            const handler = this.listeners.get('transitionend');
            if (typeof handler !== 'function') {
                throw new Error('transitionend handler missing');
            }
            handler({ propertyName });
        }
    }

    const body = new FakeElement();
    if (animatedTransitions) {
        body.classList.add('pref-animated-transitions');
    }

    const animationFrames = [];
    const timeouts = [];

    globalThis.HTMLElement = FakeElement;
    globalThis.document = { body };
    globalThis.window = {
        requestAnimationFrame(callback) {
            if (typeof callback !== 'function') {
                throw new Error('requestAnimationFrame requires callback');
            }
            animationFrames.push(callback);
        },
        setTimeout(callback) {
            if (typeof callback !== 'function') {
                throw new Error('setTimeout requires callback');
            }
            timeouts.push(callback);
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
        globalThis.window = originalWindow;
        globalThis.HTMLElement = originalHTMLElement;
    });

    return {
        createNote() {
            return new FakeElement(['note']);
        },
        runAnimationFrame() {
            const callback = animationFrames.shift();
            if (typeof callback !== 'function') {
                throw new Error('animation frame callback missing');
            }
            callback();
        },
        runTimeout() {
            const callback = timeouts.shift();
            if (typeof callback !== 'function') {
                throw new Error('timeout callback missing');
            }
            callback();
        },
    };
}

test('captureNoteCollapseAnimation returns null when animated transitions are disabled', async (t) => {
    const env = installBrowserEnvironment(t, { animatedTransitions: false });
    const { captureNoteCollapseAnimation } = await import(
        '../../app/static/js/modules/mode-manager/services/note-collapse-animation-service.js'
    );

    const note = env.createNote();
    note.dataset.isCollapsed = 'false';
    note.height = 80;

    assert.equal(captureNoteCollapseAnimation(note, true), null);
});

test('animateNoteCollapseChanges transitions from captured height to final height', async (t) => {
    const env = installBrowserEnvironment(t, { animatedTransitions: true });
    const {
        animateNoteCollapseChanges,
        captureNoteCollapseAnimation,
    } = await import(
        '../../app/static/js/modules/mode-manager/services/note-collapse-animation-service.js'
    );

    const note = env.createNote();
    note.dataset.isCollapsed = 'false';
    note.height = 80;
    const capture = captureNoteCollapseAnimation(note, true);

    note.dataset.isCollapsed = 'true';
    note.height = 20;
    animateNoteCollapseChanges([capture]);

    assert.equal(note.classList.contains('is-collapse-transitioning'), true);
    assert.equal(note.style.height, '80px');
    assert.equal(note.style.boxSizing, 'border-box');
    assert.equal(note.style.overflow, 'hidden');

    env.runAnimationFrame();

    assert.equal(note.style.height, '20px');

    note.dispatchTransitionEnd('height');

    assert.equal(note.classList.contains('is-collapse-transitioning'), false);
    assert.equal(note.style.height, '');
    assert.equal(note.style.boxSizing, '');
    assert.equal(note.style.overflow, '');

    env.runTimeout();
});
