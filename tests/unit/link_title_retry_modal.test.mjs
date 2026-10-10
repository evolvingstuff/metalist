import assert from 'node:assert/strict';
import test from 'node:test';

function createStorage() {
    const values = new Map();
    return {
        getItem: (key) => (values.has(key) ? values.get(key) : null),
        setItem: (key, value) => values.set(key, String(value)),
        removeItem: (key) => values.delete(key),
    };
}

globalThis.sessionStorage = createStorage();
globalThis.localStorage = createStorage();
globalThis.window = {};
const { describeLinkTitleRetry, describeLinkTitleRetryReason, describeLinkTitleRetryStart } = await import(
    '../../app/static/js/modules/modals/link-title-retry-modal.js'
);

const running = {
    status: 'running', total: 262, asked: 148, found: 61,
    stillFailing: { http_404: 20, http_403: 30, timeout: 37 },
    pausedSites: { 'youtube.com': 12 }, skipped: 0, dropped: 0, retryable: 0,
};

test('a running retry shows its progress, outcomes by reason and paused sites', () => {
    const view = describeLinkTitleRetry(running);
    assert.equal(view.statusLine, 'Asked 148 of 262 links');
    assert.deepEqual(view.rows, [
        { label: 'Titles found', value: '61' },
        { label: 'Still failing', value: '87' },
        { label: ' timed out', value: '37' },
        { label: ' refused by the site', value: '30' },
        { label: ' page not found', value: '20' },
        { label: 'Skipped, youtube.com asked MetaList to wait', value: '12' },
    ]);
    assert.equal(view.progressValue, 160);
    assert.equal(view.progressMax, 262);
    assert.equal(view.canStop, true);
    assert.equal(view.isActive, true);
});

test('a stopping, finished or stopped retry can no longer be stopped', () => {
    const stopping = describeLinkTitleRetry({ ...running, status: 'stopping' });
    assert.equal(stopping.statusLine, 'Stopping: finishing the lookups in progress (asked 148 of 262)');
    assert.equal(stopping.canStop, false);
    assert.equal(stopping.isActive, true);

    const stopped = describeLinkTitleRetry({ ...running, status: 'stopped', dropped: 102 });
    assert.equal(stopped.statusLine, 'Stopped: asked 148 of 262 links');
    assert.deepEqual(stopped.rows.at(-1), { label: 'Not asked (stopped)', value: '102' });
    assert.equal(stopped.isActive, false);

    const finished = describeLinkTitleRetry({ ...running, status: 'finished', asked: 250, skipped: 0 });
    assert.equal(finished.statusLine, 'Done: asked 250 of 262 links');
    assert.equal(finished.canStop, false);
    assert.equal(finished.isActive, false);
});

test('a single link reads as one link', () => {
    const view = describeLinkTitleRetry({ ...running, status: 'finished', total: 1, asked: 1, found: 1,
        stillFailing: {}, pausedSites: {} });
    assert.equal(view.statusLine, 'Done: asked 1 of 1 link');
});

test('reasons read as plain words, unknown HTTP codes as HTTP n', () => {
    assert.equal(describeLinkTitleRetryReason('http_429'), 'too many requests');
    assert.equal(describeLinkTitleRetryReason('interstitial_title'), 'login, consent or verification page');
    assert.equal(describeLinkTitleRetryReason('http_999'), 'HTTP 999');
    assert.equal(describeLinkTitleRetryReason('too_many_redirects'), 'too many redirects');
});

test('malformed progress fails loudly', () => {
    assert.throws(() => describeLinkTitleRetry({ ...running, status: 'paused' }), /known status/);
    assert.throws(() => describeLinkTitleRetry({ ...running, asked: -1 }), /asked/);
    assert.throws(() => describeLinkTitleRetry({ ...running, pausedSites: [] }), /pausedSites/);
});

test('before a run the dialog offers to ask the failed links again, or says there are none', () => {
    assert.deepEqual(describeLinkTitleRetryStart(261),
        { statusLine: '261 failed link titles can be asked again.', startLabel: 'Retry 261 links' });
    assert.deepEqual(describeLinkTitleRetryStart(1),
        { statusLine: '1 failed link title can be asked again.', startLabel: 'Retry 1 link' });
    assert.deepEqual(describeLinkTitleRetryStart(0),
        { statusLine: 'No failed link titles to retry.', startLabel: '' });
});
