import assert from 'node:assert/strict';
import test from 'node:test';

import {
    classifyApiFailure,
} from '../../app/static/js/modules/api-failure-classification-service.js';


test('HTTP failures do not claim that connectivity was lost', () => {
    assert.deepEqual(classifyApiFailure(null, { status: 500 }), {
        kind: 'http',
        message: 'Server error (500). Please try again.',
    });
    assert.deepEqual(classifyApiFailure(null, { status: 422 }), {
        kind: 'http',
        message: 'Request failed (422). Please check your input and try again.',
    });
});


test('authentication failures retain their dedicated logout path', () => {
    assert.deepEqual(classifyApiFailure(null, { status: 401 }), {
        kind: 'auth',
        message: 'Your session has expired. Please log in again.',
    });
});


test('transport failures are the only failures classified as disconnected', () => {
    assert.deepEqual(classifyApiFailure(
        new TypeError('Failed to fetch'),
        null,
    ), {
        kind: 'network',
        message: 'We\u2019ve lost touch with the MetaList server. Editing is paused while we reconnect.',
    });
    assert.deepEqual(classifyApiFailure(
        new DOMException('Timed out', 'AbortError'),
        null,
    ), {
        kind: 'network',
        message: 'The MetaList server is taking a little longer to respond. Editing is paused while we reconnect.',
    });
});


test('internal exceptions are not disguised as connectivity failures', () => {
    const internalError = new Error('Malformed response payload');
    assert.deepEqual(classifyApiFailure(internalError, null), {
        kind: 'internal',
        error: internalError,
    });
});
