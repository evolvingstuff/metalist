import assert from 'node:assert/strict';
import test from 'node:test';

import {
    rejectedInputWarning,
    shouldSuppressFatalOverlay,
} from '../../app/static/js/modules/error-overlay.js';
import { HttpRequestError, ServerInputRejectedError } from '../../app/static/js/modules/expected-errors.js';


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


test('input the server rejected becomes a polite warning, other failures do not', () => {
    assert.equal(
        rejectedInputWarning(new ServerInputRejectedError("Unclosed quote '\"' in search query")),
        "That could not be used: Unclosed quote '\"' in search query.",
    );
    // Unexpected failures stay fatal and loud.
    assert.equal(rejectedInputWarning(new HttpRequestError('API call failed: 500 Internal Server Error')), null);
    assert.equal(rejectedInputWarning(new Error('Malformed response payload')), null);
});
