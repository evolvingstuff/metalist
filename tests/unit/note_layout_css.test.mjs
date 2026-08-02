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
