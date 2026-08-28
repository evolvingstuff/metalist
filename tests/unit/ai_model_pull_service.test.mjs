import assert from 'node:assert/strict';
import test from 'node:test';

import {
    parseModelPullNdjsonBuffer,
} from '../../app/static/js/modules/ai-chat/ai-chat-api.js';


test('model pull parser retains partial events and validates progress', () => {
    const parsed = parseModelPullNdjsonBuffer(
        '{"type":"progress","status":"pulling layer","completed":25,"total":100}\n'
        + '{"type":"done"',
    );

    assert.deepEqual(parsed.events, [
        {
            type: 'progress',
            status: 'pulling layer',
            completed: 25,
            total: 100,
        },
    ]);
    assert.equal(parsed.remainder, '{"type":"done"');
});


test('model pull parser accepts a typed error event', () => {
    const parsed = parseModelPullNdjsonBuffer(
        '{"type":"error","message":"download failed"}\n',
    );

    assert.deepEqual(parsed.events, [
        { type: 'error', message: 'download failed' },
    ]);
    assert.equal(parsed.remainder, '');
});


test('model pull parser rejects malformed progress bytes', () => {
    assert.throws(
        () => parseModelPullNdjsonBuffer(
            '{"type":"progress","status":"pulling","completed":-1,"total":100}\n',
        ),
        /valid completed bytes/,
    );
});
