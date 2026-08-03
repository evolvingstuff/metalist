import assert from 'node:assert/strict';
import test from 'node:test';

import { waitForCommandAvailability } from '../../app/static/js/modules/command-palette/backup-command-availability.js';


test('backup command waits until the browser command gate is idle', async () => {
    let isBusy = true;
    let busyChecks = 0;
    setTimeout(() => {
        isBusy = false;
    }, 5);

    await waitForCommandAvailability({
        isBusy: () => {
            busyChecks += 1;
            return isBusy;
        },
        isLoading: () => false,
        timeoutMs: 100,
        pollIntervalMs: 1,
    });

    assert.equal(isBusy, false);
    assert.ok(busyChecks > 1);
});


test('backup command waits until browser loading finishes', async () => {
    let isLoading = true;
    setTimeout(() => {
        isLoading = false;
    }, 5);

    await waitForCommandAvailability({
        isBusy: () => false,
        isLoading: () => isLoading,
        timeoutMs: 100,
        pollIntervalMs: 1,
    });

    assert.equal(isLoading, false);
});


test('backup command fails loudly when browser state never becomes available', async () => {
    await assert.rejects(
        waitForCommandAvailability({
            isBusy: () => true,
            isLoading: () => false,
            timeoutMs: 5,
            pollIntervalMs: 1,
        }),
        /Timed out waiting to start backup/,
    );
});
