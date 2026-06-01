import assert from 'node:assert/strict';
import test from 'node:test';

import { CONFIG } from '../../app/static/js/modules/config.js';
import {
    normalizeSoftWrappedTextLineBreaks,
    splitMeaningfulTextLineBreaks,
    sanitizePastedImageSourceUrl,
    sanitizeStyleAttributeValue,
    sanitizeUrlAttributeValue,
} from '../../app/static/js/modules/mode-manager/services/html-paste-sanitizer-service.js';

test('sanitizeUrlAttributeValue keeps safe https href', () => {
    const value = sanitizeUrlAttributeValue('https://example.com/path?q=1', 'href');
    assert.equal(value, 'https://example.com/path?q=1');
});

test('sanitizeUrlAttributeValue strips javascript href', () => {
    const value = sanitizeUrlAttributeValue('javascript:alert(1)', 'href');
    assert.equal(value, null);
});

test('sanitizeUrlAttributeValue strips percent-encoded javascript href', () => {
    const value = sanitizeUrlAttributeValue('j%61vascript:alert(1)', 'href');
    assert.equal(value, null);
});

test('sanitizeUrlAttributeValue allows safe data image src under byte limit', () => {
    const value = sanitizeUrlAttributeValue('data:image/png;base64,AAAA', 'src');
    assert.equal(value, 'data:image/png;base64,AAAA');
});

test('sanitizeUrlAttributeValue rejects over-limit data image src', () => {
    const maxBytes = CONFIG.PASTE.MAX_DATA_IMAGE_BYTES;
    const payloadLength = Math.ceil(((maxBytes + 1) * 4) / 3);
    const payload = 'A'.repeat(payloadLength);
    const value = sanitizeUrlAttributeValue(`data:image/png;base64,${payload}`, 'src');
    assert.equal(value, null);
});

test('sanitizePastedImageSourceUrl keeps oversized data image src for later recompression', () => {
    const maxBytes = CONFIG.PASTE.MAX_DATA_IMAGE_BYTES;
    const payloadLength = Math.ceil(((maxBytes + 1) * 4) / 3);
    const payload = 'A'.repeat(payloadLength);
    const value = sanitizePastedImageSourceUrl(`data:image/png;base64,${payload}`);
    assert.equal(value, `data:image/png;base64,${payload}`);
});

test('sanitizePastedImageSourceUrl rejects non-image data urls', () => {
    const value = sanitizePastedImageSourceUrl('data:text/html;base64,AAAA');
    assert.equal(value, null);
});

test('sanitizeStyleAttributeValue keeps safe block indentation styles', () => {
    const value = sanitizeStyleAttributeValue('margin-left: 24px; text-indent: 0px;', 'div');
    assert.equal(value, 'margin-left: 24px; text-indent: 0px;');
});

test('sanitizeStyleAttributeValue keeps numeric vertical align for copied math superscripts', () => {
    const value = sanitizeStyleAttributeValue('vertical-align: 0.5em; color: red;', 'span');
    assert.equal(value, 'vertical-align: 0.5em;');
});

test('sanitizeStyleAttributeValue strips unsafe styles and disallowed properties', () => {
    const value = sanitizeStyleAttributeValue('position: absolute; color: red; margin-left: 12px; background-image: url(https://x);', 'div');
    assert.equal(value, 'margin-left: 12px;');
});

test('sanitizeStyleAttributeValue removes encoded entity payloads', () => {
    const value = sanitizeStyleAttributeValue('margin-left: &#x31;2px;', 'div');
    assert.equal(value, null);
});

test('splitMeaningfulTextLineBreaks preserves YouTube literal timestamp newlines', () => {
    const parts = splitMeaningfulTextLineBreaks('\n\nTimestamps:\n(0:00) - Intro\r\n(0:18) - Rule');
    assert.deepEqual(parts, [
        '',
        '',
        'Timestamps:',
        '(0:00) - Intro',
        '(0:18) - Rule',
    ]);
});

test('splitMeaningfulTextLineBreaks ignores formatting-only HTML whitespace', () => {
    const parts = splitMeaningfulTextLineBreaks('\n    \n  ');
    assert.equal(parts, null);
});

test('normalizeSoftWrappedTextLineBreaks joins wrapped arXiv abstract prose', () => {
    const input = 'formal languages in the complexity class AC0,\n'
        + 'the class of languages recognizable by families of Boolean circuits of\n'
        + 'constant depth and polynomial size. In contrast, the non-\n'
        + 'AC0 languages MAJORITY and DYCK-1 are recognizable.';

    const normalized = normalizeSoftWrappedTextLineBreaks(input);

    assert.equal(
        normalized,
        'formal languages in the complexity class AC0, the class of languages recognizable by families of Boolean circuits of constant depth and polynomial size. In contrast, the non-AC0 languages MAJORITY and DYCK-1 are recognizable.',
    );
});

test('normalizeSoftWrappedTextLineBreaks keeps real arXiv abstract paragraph breaks', () => {
    const input = 'heads.\n\nOur results feature several implications unique to the attention structure.';

    const normalized = normalizeSoftWrappedTextLineBreaks(input);

    assert.equal(normalized, input);
});

test('normalizeSoftWrappedTextLineBreaks keeps timestamp lists as explicit line breaks', () => {
    const input = 'Timestamps:\n(0:00) - Intro\n(0:18) - Rule';

    const normalized = normalizeSoftWrappedTextLineBreaks(input);

    assert.equal(normalized, input);
});
