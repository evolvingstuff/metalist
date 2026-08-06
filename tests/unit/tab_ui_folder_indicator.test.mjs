import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const TEMPLATE_URL = new URL('../../app/templates/index.html', import.meta.url);
const CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);


test('enabled tabs expose a white outline folder indicator inside the hover trigger', async () => {
    const [templateSource, cssSource] = await Promise.all([
        readFile(TEMPLATE_URL, 'utf8'),
        readFile(CSS_URL, 'utf8'),
    ]);

    const hoverZoneStart = templateSource.indexOf('id="tab-hover-zone"');
    const hoverZoneEnd = templateSource.indexOf('</div>', hoverZoneStart);
    const hoverZoneSource = templateSource.slice(hoverZoneStart, hoverZoneEnd);

    assert.ok(hoverZoneStart >= 0);
    assert.ok(hoverZoneEnd > hoverZoneStart);
    assert.match(hoverZoneSource, /class="tab-ui-folder-icon"/);
    assert.match(hoverZoneSource, /<path /);
    assert.match(cssSource, /\.controls \.tab-ui-folder-icon\s*\{[\s\S]*stroke: #ffffff;/);
    assert.match(
        cssSource,
        /body\.pref-show-tab-ui \.controls \.tab-ui-folder-icon\s*\{[\s\S]*opacity: 0\.78;/,
    );
});
