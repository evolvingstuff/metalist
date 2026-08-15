import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const TEMPLATE_URL = new URL('../../app/templates/index.html', import.meta.url);
const CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);
const MOUSE_EVENTS_URL = new URL(
    '../../app/static/js/modules/mode-manager/events/mouse-events.js',
    import.meta.url,
);

test('reference source navigation uses a dismissible mode indicator instead of a back arrow', async () => {
    const [template, css, mouseEvents] = await Promise.all([
        readFile(TEMPLATE_URL, 'utf8'),
        readFile(CSS_URL, 'utf8'),
        readFile(MOUSE_EVENTS_URL, 'utf8'),
    ]);

    assert.doesNotMatch(template, /id="reference-back-button"/);
    assert.match(template, /id="reference-source-indicator"[^>]*hidden/);
    assert.match(template, /class="reference-source-indicator-label">Reference source</);
    assert.match(template, /id="reference-source-indicator-clear"/);
    assert.match(css, /\.controls \.reference-source-indicator/);
    assert.match(css, /\.controls \.reference-source-indicator-clear/);
    assert.match(
        mouseEvents,
        /event\.target\.closest\('#reference-source-indicator-clear'\)/,
    );
    assert.match(mouseEvents, /await navigateBackFromReferenceContext\(\)/);
});
