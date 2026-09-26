import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';


const MAIN_CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);
const NOTES_TEMPLATE_URL = new URL('../../app/templates/notes_list.html', import.meta.url);


test('note layout CSS sizes root notes without enlarging their children', () => {
    const css = readFileSync(MAIN_CSS_URL, 'utf8');
    const notesTemplate = readFileSync(NOTES_TEMPLATE_URL, 'utf8');

    assert.match(css, /\.note\[data-parent-id=""\]\s*>\s*\.note-content/);
    assert.match(notesTemplate, /data-parent-id="\$\{note\.get\('parent_id'\) or ''\}"/);
    assert.match(css, /body\[data-top-level-note-size="larger"\]/);
    assert.match(css, /body\[data-child-indentation="wide"\]/);
    assert.match(css, /body\[data-note-vertical-spacing="spacious"\]/);
});


test('visible note tags wrap within one quarter of the note row', () => {
    const css = readFileSync(MAIN_CSS_URL, 'utf8');

    assert.match(css, /body\.pref-show-note-tags\s+\.note-tags\s*\{[^}]*max-width:\s*25%/s);
    assert.match(css, /body\.pref-show-note-tags\s+\.note-tags\s*\{[^}]*overflow-wrap:\s*anywhere/s);
});


test('a single line of visible note tags adds no vertical spacing', () => {
    const css = readFileSync(MAIN_CSS_URL, 'utf8');

    assert.match(css, /\.note-tags\s*\{[^}]*padding:\s*0 8px;/s);
    assert.doesNotMatch(css, /\.note-tags\s*\{[^}]*margin-bottom:/s);
});


test('every corner preset sets root and nested radii that notes and the preview use', () => {
    const css = readFileSync(MAIN_CSS_URL, 'utf8');

    for (const preset of ['subtle', 'rounded', 'round']) {
        const rule = new RegExp(
            `body\\[data-note-corners="${preset}"\\],\\s*\\.note-layout-preview\\[data-note-corners="${preset}"\\]\\s*\\{[^}]*--note-corner-radius:[^}]*--note-corner-radius-nested:`,
            's',
        );
        assert.match(css, rule);
    }
    assert.match(css, /\.note\s*\{[^}]*border-radius:\s*var\(--note-corner-radius\)/s);
    assert.match(css, /\.note-children\s+\.note\s*\{[^}]*border-radius:\s*var\(--note-corner-radius-nested\)/s);
});


test('tag style presets switch note tags between pills and plain text in every theme', () => {
    const css = readFileSync(MAIN_CSS_URL, 'utf8');

    for (const preset of ['pills', 'text']) {
        assert.match(css, new RegExp(`body\\[data-tag-style="${preset}"\\],\\s*\\.note-layout-preview\\[data-tag-style="${preset}"\\]`));
    }
    assert.match(css, /\.note-tag\s*\{[^}]*border:\s*var\(--note-tag-border-width\) solid var\(--note-tag-border\)/s);
    assert.doesNotMatch(css, /html\[data-theme="dark"\]\s+\.note-tag\s*\{/);
});


test('the note being edited glows in the dark theme, the inverse of the light theme shadow', () => {
    const css = readFileSync(MAIN_CSS_URL, 'utf8');
    const rule = css.match(/html\[data-theme="dark"\] \.note\.editing\s*\{([^}]*)\}/);
    assert.ok(rule, 'expected a dark theme editing note rule');
    const shadow = rule[1].match(/box-shadow:([^;]*);/);
    assert.ok(shadow, 'expected a box-shadow on the edited note');
    assert.match(shadow[1], /0 0 \d+px rgba\(255, 255, 255, 0\.\d+\)/);
});
