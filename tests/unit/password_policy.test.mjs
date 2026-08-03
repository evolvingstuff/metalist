import assert from 'node:assert/strict';
import test from 'node:test';

import {
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    validateNewPasswordLength,
} from '../../app/static/js/modules/password-policy.js';


test('new-password length policy matches the server limits', () => {
    assert.equal(PASSWORD_MIN_LENGTH, 12);
    assert.equal(PASSWORD_MAX_LENGTH, 72);
    assert.deepEqual(validateNewPasswordLength('x'.repeat(11)), {
        valid: false,
        error: 'Password must be at least 12 characters',
    });
    assert.deepEqual(validateNewPasswordLength('x'.repeat(73)), {
        valid: false,
        error: 'Password must be no more than 72 characters',
    });
    assert.deepEqual(validateNewPasswordLength('a spacious passphrase'), { valid: true });
});
