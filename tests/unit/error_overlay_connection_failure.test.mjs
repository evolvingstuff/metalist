import assert from 'node:assert/strict';
import test from 'node:test';

import {
    shouldSuppressFatalOverlay,
} from '../../app/static/js/modules/error-overlay.js';


test('expected connection failures do not become fatal error dumps', () => {
    assert.equal(shouldSuppressFatalOverlay(new TypeError('Failed to fetch')), true);
    assert.equal(
        shouldSuppressFatalOverlay(new DOMException('Timed out', 'AbortError')),
        true,
    );
});


test('unexpected client failures still reach the fatal error overlay', () => {
    assert.equal(
        shouldSuppressFatalOverlay(new Error('Malformed response payload')),
        false,
    );
});
