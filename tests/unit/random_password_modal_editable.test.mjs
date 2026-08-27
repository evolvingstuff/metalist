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


test('password length uses one compact value-and-unit control without a redundant summary card', () => {
    const source = readFileSync(MODAL_SOURCE_URL, 'utf8');
    const css = readFileSync(new URL('../../app/static/css/main.css', import.meta.url), 'utf8');

    assert.match(source, /<span class="random-password-length-unit">characters<\/span>/);
    assert.match(source, /const MAX_PASSWORD_LENGTH = 72;/);
    assert.match(source, /max="\$\{MAX_PASSWORD_LENGTH\}"/);
    assert.doesNotMatch(source, /1024/);
    assert.doesNotMatch(source, /password-character-count/);
    assert.doesNotMatch(source, /random-password-summary-card/);
    assert.match(css, /\.random-password-length-control input \{[\s\S]*?width:\s*60px/);
    assert.match(css, /random-password-modal-content textarea \{[\s\S]*?440px/);
});
