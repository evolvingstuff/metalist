import assert from 'node:assert/strict';
import test from 'node:test';

import { CONFIG } from '../../app/static/js/modules/config.js';
import {
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

test('sanitizeStyleAttributeValue strips unsafe styles and disallowed properties', () => {
    const value = sanitizeStyleAttributeValue('position: absolute; color: red; margin-left: 12px; background-image: url(https://x);', 'div');
    assert.equal(value, 'margin-left: 12px;');
});

test('sanitizeStyleAttributeValue removes encoded entity payloads', () => {
    const value = sanitizeStyleAttributeValue('margin-left: &#x31;2px;', 'div');
    assert.equal(value, null);
});
