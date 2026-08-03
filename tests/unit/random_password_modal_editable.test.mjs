import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const MODAL_SOURCE_URL = new URL(
    '../../app/static/js/modules/modals/random-password-modal.js',
    import.meta.url,
);


test('password result accepts typed candidates and rescoring input in real time', () => {
    const source = readFileSync(MODAL_SOURCE_URL, 'utf8');
    const resultInputMarkup = source.match(
        /<input(?=[^>]*id="password-result-output")[^>]*>/,
    );

    assert.ok(resultInputMarkup, 'password-result-output markup missing');
    assert.doesNotMatch(resultInputMarkup[0], /\breadonly\b/);
    assert.match(source, /resultOutput\.oninput\s*=/);
    assert.match(source, /this\.renderPasswordStrength\(resultOutput\.value\)/);
});
