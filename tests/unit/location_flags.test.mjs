import assert from 'node:assert/strict';
import test from 'node:test';

import { consumeBooleanQueryFlag } from '../../app/static/js/modules/location-flags.js';


test('consumeBooleanQueryFlag removes a matching flag and returns true', () => {
    const calls = [];
    const consumed = consumeBooleanQueryFlag({
        location: {
            href: 'http://127.0.0.1:8000/?force_reauth=1&view=notes#section',
        },
        history: {
            replaceState: (...args) => calls.push(args),
        },
        flagName: 'force_reauth',
    });

    assert.equal(consumed, true);
    assert.deepEqual(calls, [[{}, '', '/?view=notes#section']]);
});


test('consumeBooleanQueryFlag leaves the URL unchanged when the flag is absent', () => {
    const calls = [];
    const consumed = consumeBooleanQueryFlag({
        location: {
            href: 'http://127.0.0.1:8000/?view=notes#section',
        },
        history: {
            replaceState: (...args) => calls.push(args),
        },
        flagName: 'force_reauth',
    });

    assert.equal(consumed, false);
    assert.deepEqual(calls, []);
});
