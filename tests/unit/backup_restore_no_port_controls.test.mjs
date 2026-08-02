import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


test('restore confirmation never renders launch port controls', async () => {
    const sourceUrl = new URL(
        '../../app/static/js/modules/modals/backup-restore-modal.js',
        import.meta.url,
    );
    const source = await readFile(sourceUrl, 'utf8');

    assert.doesNotMatch(source, /Launch Ports For Imported Namespace/);
    assert.doesNotMatch(source, /backup-restore-port-input/);
});
