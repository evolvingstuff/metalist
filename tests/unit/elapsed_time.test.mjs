import assert from 'node:assert/strict';
import test from 'node:test';

import { formatElapsedDuration } from '../../app/static/js/modules/elapsed-time.js';


test('elapsed duration reports whole seconds below one minute', () => {
    assert.equal(formatElapsedDuration(0), '0s');
    assert.equal(formatElapsedDuration(12_999), '12s');
});


test('elapsed duration reports minutes and seconds for long hydration', () => {
    assert.equal(formatElapsedDuration(60_000), '1m 0s');
    assert.equal(formatElapsedDuration(243_900), '4m 3s');
});


test('elapsed duration rejects invalid measurements', () => {
    assert.throws(() => formatElapsedDuration(-1), /non-negative finite number/);
    assert.throws(() => formatElapsedDuration(Number.NaN), /non-negative finite number/);
});
