import assert from 'node:assert/strict';
import test from 'node:test';

import { describeApiFailure } from '../../app/static/js/modules/api-error-diagnostics.js';

test('500 includes safe server diagnostic in the visible error', async () => {
    const response = new Response(JSON.stringify({
        detail: 'Internal server error',
        diagnostic: { errorType: 'ValueError', codeLocation: 'app/api/routes/notes.py:42' },
    }), { status: 500, statusText: 'Internal Server Error', headers: { 'content-type': 'application/json' } });

    assert.equal(
        await describeApiFailure(response),
        'API call failed: 500 Internal Server Error (ValueError at app/api/routes/notes.py:42)',
    );
});

test('unrecognized and non-500 bodies are not shown in the visible error', async () => {
    const body = JSON.stringify({ diagnostic: {
        errorType: 'ValueError', codeLocation: 'C:/Users/private/notes.txt:42',
    }, secret: 'PRIVATE_NOTE_CONTENT' });
    const serverError = new Response(body, { status: 500, statusText: 'Internal Server Error', headers: { 'content-type': 'application/json' } });
    const badRequest = new Response(body, { status: 400, statusText: 'Bad Request', headers: { 'content-type': 'application/json' } });
    const traversal = new Response(JSON.stringify({ diagnostic: {
        errorType: 'ValueError', codeLocation: 'app/../../private.py:42',
    } }), { status: 500, statusText: 'Internal Server Error', headers: { 'content-type': 'application/json' } });

    assert.equal(await describeApiFailure(serverError), 'API call failed: 500 Internal Server Error');
    assert.equal(await describeApiFailure(badRequest), 'API call failed: 400 Bad Request');
    assert.equal(await describeApiFailure(traversal), 'API call failed: 500 Internal Server Error');
});
