import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const MAIN_CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);

test('note reference anchors only occupy their visible link content', async () => {
    const css = await readFile(MAIN_CSS_URL, 'utf8');

    assert.match(
        css,
        /\.note-reference-link\s*\{[^}]*display:\s*inline-flex;[^}]*max-width:\s*100%;[^}]*\}/s,
    );
    assert.match(
        css,
        /\.note\.collapsed:not\(\.editing\)[^{]*\.note-reference-link\s*\{[^}]*display:\s*inline-flex;[^}]*\}/s,
    );
});
