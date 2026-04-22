import assert from 'node:assert/strict';
import test from 'node:test';

class TestElement {
    constructor(id, disabled = false) {
        this.id = id;
        this._disabled = disabled;
        this.focusCount = 0;
    }

    hasAttribute(name) {
        if (name !== 'disabled') {
            return false;
        }
        return this._disabled;
    }

    focus() {
        this.focusCount += 1;
    }
}

class TestInputElement extends TestElement {}
class TestButtonElement extends TestElement {}

test('BackupSettingsModal focuses the first enabled control inside the modal', async (t) => {
    const originalSessionStorage = globalThis.sessionStorage;
    const originalDocument = globalThis.document;
    const originalHTMLElement = globalThis.HTMLElement;

    globalThis.sessionStorage = {
        getItem() {
            return null;
        },
        setItem() {},
    };
    globalThis.HTMLElement = TestElement;

    const retentionInput = new TestInputElement('backup-settings-retention-count');
    const folderPickButton = new TestButtonElement('backup-settings-folder-pick-btn');
    const runButton = new TestButtonElement('backup-settings-run-btn');
    const cancelButton = new TestButtonElement('backup-settings-cancel-btn');

    const elements = new Map([
        ['backup-settings-retention-count', retentionInput],
        ['backup-settings-folder-pick-btn', folderPickButton],
        ['backup-settings-run-btn', runButton],
        ['backup-settings-cancel-btn', cancelButton],
    ]);

    globalThis.document = {
        getElementById(id) {
            return elements.get(id) ?? null;
        },
    };

    t.after(() => {
        if (typeof originalSessionStorage === 'undefined') {
            delete globalThis.sessionStorage;
        } else {
            globalThis.sessionStorage = originalSessionStorage;
        }
        if (typeof originalDocument === 'undefined') {
            delete globalThis.document;
        } else {
            globalThis.document = originalDocument;
        }
        if (typeof originalHTMLElement === 'undefined') {
            delete globalThis.HTMLElement;
        } else {
            globalThis.HTMLElement = originalHTMLElement;
        }
    });

    const { BackupSettingsModal } = await import('../../app/static/js/modules/modals/backup-settings-modal.js');
    const modal = new BackupSettingsModal();

    modal._focusPreferredControl();

    assert.equal(retentionInput.focusCount, 1);
    assert.equal(folderPickButton.focusCount, 0);
    assert.equal(runButton.focusCount, 0);
    assert.equal(cancelButton.focusCount, 0);
});

test('BackupSettingsModal falls back to the next enabled control when retention is disabled', async (t) => {
    const originalSessionStorage = globalThis.sessionStorage;
    const originalDocument = globalThis.document;
    const originalHTMLElement = globalThis.HTMLElement;

    globalThis.sessionStorage = {
        getItem() {
            return null;
        },
        setItem() {},
    };
    globalThis.HTMLElement = TestElement;

    const retentionInput = new TestInputElement('backup-settings-retention-count', true);
    const folderPickButton = new TestButtonElement('backup-settings-folder-pick-btn', true);
    const runButton = new TestButtonElement('backup-settings-run-btn', true);
    const cancelButton = new TestButtonElement('backup-settings-cancel-btn');

    const elements = new Map([
        ['backup-settings-retention-count', retentionInput],
        ['backup-settings-folder-pick-btn', folderPickButton],
        ['backup-settings-run-btn', runButton],
        ['backup-settings-cancel-btn', cancelButton],
    ]);

    globalThis.document = {
        getElementById(id) {
            return elements.get(id) ?? null;
        },
    };

    t.after(() => {
        if (typeof originalSessionStorage === 'undefined') {
            delete globalThis.sessionStorage;
        } else {
            globalThis.sessionStorage = originalSessionStorage;
        }
        if (typeof originalDocument === 'undefined') {
            delete globalThis.document;
        } else {
            globalThis.document = originalDocument;
        }
        if (typeof originalHTMLElement === 'undefined') {
            delete globalThis.HTMLElement;
        } else {
            globalThis.HTMLElement = originalHTMLElement;
        }
    });

    const { BackupSettingsModal } = await import('../../app/static/js/modules/modals/backup-settings-modal.js');
    const modal = new BackupSettingsModal();

    modal._focusPreferredControl();

    assert.equal(cancelButton.focusCount, 1);
    assert.equal(retentionInput.focusCount, 0);
    assert.equal(folderPickButton.focusCount, 0);
    assert.equal(runButton.focusCount, 0);
});
