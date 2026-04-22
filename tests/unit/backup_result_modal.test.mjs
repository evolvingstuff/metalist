import assert from 'node:assert/strict';
import test from 'node:test';

const originalSessionStorage = globalThis.sessionStorage;
globalThis.sessionStorage = {
    getItem() {
        return null;
    },
    setItem() {},
};

const { formatBackupSize } = await import('../../app/static/js/modules/modals/backup-result-modal.js');

if (typeof originalSessionStorage === 'undefined') {
    delete globalThis.sessionStorage;
} else {
    globalThis.sessionStorage = originalSessionStorage;
}

test('formatBackupSize formats bytes across common archive sizes', () => {
    assert.equal(formatBackupSize(512), '512 B');
    assert.equal(formatBackupSize(1536), '1.5 KB');
    assert.equal(formatBackupSize(3 * 1024 * 1024), '3.0 MB');
});

test('formatBackupSize rejects negative sizes', () => {
    assert.throws(
        () => formatBackupSize(-1),
        /sizeBytes must be a non-negative integer/,
    );
});
