import assert from 'node:assert/strict';
import test from 'node:test';

import {
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    calculatePasswordLengthProgress,
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


test('minimum-length progress fills at 12 characters and stays capped', () => {
    assert.deepEqual(calculatePasswordLengthProgress(''), {
        characterCount: 0,
        remainingCharacterCount: 12,
        progressPercent: 0,
        meetsMinimumLength: false,
    });
    assert.deepEqual(calculatePasswordLengthProgress('x'.repeat(6)), {
        characterCount: 6,
        remainingCharacterCount: 6,
        progressPercent: 50,
        meetsMinimumLength: false,
    });
    assert.deepEqual(calculatePasswordLengthProgress('x'.repeat(12)), {
        characterCount: 12,
        remainingCharacterCount: 0,
        progressPercent: 100,
        meetsMinimumLength: true,
    });
    assert.deepEqual(calculatePasswordLengthProgress('x'.repeat(20)), {
        characterCount: 20,
        remainingCharacterCount: 0,
        progressPercent: 100,
        meetsMinimumLength: true,
    });
});
