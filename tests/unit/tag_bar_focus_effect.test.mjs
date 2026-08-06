import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);


test('tag bar focus has a persistent cue and an optional one-shot halo', async () => {
    const cssSource = await readFile(CSS_URL, 'utf8');

    assert.match(
        cssSource,
        /\.note-tag-bar:focus-within\s*\{[\s\S]*border-color:[\s\S]*box-shadow:/,
    );
    assert.match(
        cssSource,
        /body\.pref-animated-transitions \.note-tag-bar:focus-within::after\s*\{[\s\S]*animation: note-tag-bar-focus-halo 520ms/,
    );
    assert.match(cssSource, /@keyframes note-tag-bar-focus-halo/);
    assert.match(
        cssSource,
        /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.note-tag-bar:focus-within::after[\s\S]*animation: none;/,
    );
});
