import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const MAIN_CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);


function cssRule(source, selector, nextSelector) {
    const start = source.indexOf(selector);
    const end = source.indexOf(nextSelector, start);
    assert.notEqual(start, -1, `${selector} rule missing`);
    assert.notEqual(end, -1, `${nextSelector} rule missing`);
    return source.slice(start, end);
}


test('command palette input remains inside a stable viewport-safe panel', () => {
    const source = readFileSync(MAIN_CSS_URL, 'utf8');
    const modalRule = cssRule(source, '.command-palette-modal {', '.command-palette-panel');
    const panelRule = cssRule(source, '.command-palette-panel {', '.command-palette-input-row');
    const inputRule = cssRule(source, '.command-palette-input {', '.command-palette-input:focus');

    assert.match(modalRule, /overflow:\s*hidden/);
    assert.match(modalRule, /padding:\s*0/);
    assert.match(panelRule, /width:\s*min\(860px, 92vw\)/);
    assert.match(panelRule, /box-sizing:\s*border-box/);
    assert.match(inputRule, /width:\s*100%/);
    assert.match(inputRule, /box-sizing:\s*border-box/);
    assert.match(inputRule, /min-width:\s*0/);
});
