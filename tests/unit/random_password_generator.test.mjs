import assert from 'node:assert/strict';
import test from 'node:test';

import {
    generateRandomPassword,
    normalizePasswordCharset,
} from '../../app/static/js/modules/password-generator.js';

test('normalizePasswordCharset strips newline separators', () => {
    const normalized = normalizePasswordCharset('abc\nXYZ\r\n123');
    assert.equal(normalized, 'abcXYZ123');
});

test('generateRandomPassword uses provided random source deterministically', () => {
    const deterministicRandom = (buffer) => {
        for (let index = 0; index < buffer.length; index += 1) {
            buffer[index] = index;
        }
        return buffer;
    };

    const password = generateRandomPassword(6, 'abc', deterministicRandom);
    assert.equal(password, 'abcabc');
});

test('generateRandomPassword rejects invalid length', () => {
    assert.throws(
        () => generateRandomPassword(0, 'abc', () => new Uint32Array(0)),
        /length must be a positive integer/,
    );
});

test('generateRandomPassword rejects empty charset', () => {
    assert.throws(
        () => generateRandomPassword(8, '', () => new Uint32Array(0)),
        /charset must be a non-empty string/,
    );
});
