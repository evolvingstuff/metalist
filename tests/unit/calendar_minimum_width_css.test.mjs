import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';


const MAIN_CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);


test('visible calendar keeps a usable width in the intermediate desktop range', () => {
    const source = readFileSync(MAIN_CSS_URL, 'utf8');

    assert.match(source, /--rhs-calendar-min-width:\s*160px;/);
    assert.match(
        source,
        /@media \(min-width: 961px\) and \(max-width: 1235px\)[\s\S]*?\.rhs-panel,[\s\S]*?\.rhs-metric-toggle[\s\S]*?width:\s*var\(--rhs-calendar-min-width\);/,
    );
    assert.match(
        source,
        /body\.pref-show-rhs-panel #app\s*\{[\s\S]*?width:\s*min\(var\(--app-shell-width\), calc\(100vw - var\(--rhs-reserved-width\)\)\);[\s\S]*?margin-left:\s*max\(\s*0px,/,
    );
});
