import assert from 'node:assert/strict';
import test from 'node:test';

import { AuthenticationRequiredError } from '../../app/static/js/modules/client-state-api.js';
import { persistUsageBeforeActivation } from '../../app/static/js/modules/command-palette/activation-auth-policy.js';


test('expired session blocks command activation and requests a clean logout', async () => {
    const logoutMessages = [];

    const canActivate = await persistUsageBeforeActivation({
        persistUsage: async () => {
            throw new AuthenticationRequiredError('Authentication required');
        },
        handleAuthenticationRequired: (message) => {
            logoutMessages.push(message);
        },
    });

    assert.equal(canActivate, false);
    assert.deepEqual(logoutMessages, ['Your session has expired. Please log in again.']);
});


test('successful usage persistence permits command activation', async () => {
    let persistenceCalls = 0;

    const canActivate = await persistUsageBeforeActivation({
        persistUsage: async () => {
            persistenceCalls += 1;
        },
        handleAuthenticationRequired: () => {
            throw new Error('Authentication handler must not run');
        },
    });

    assert.equal(canActivate, true);
    assert.equal(persistenceCalls, 1);
});


test('unexpected usage persistence failures remain fatal', async () => {
    const persistenceError = new Error('Database write failed');

    await assert.rejects(
        persistUsageBeforeActivation({
            persistUsage: async () => {
                throw persistenceError;
            },
            handleAuthenticationRequired: () => {
                throw new Error('Authentication handler must not run');
            },
        }),
        (error) => error === persistenceError,
    );
});
