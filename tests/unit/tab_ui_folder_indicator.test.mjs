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
    assert.match(hoverZoneSource, /class="tab-ui-folder-icon-back"/);
    assert.match(hoverZoneSource, /class="tab-ui-folder-icon-front"/);
    assert.match(
        hoverZoneSource,
        /class="tab-ui-folder-icon-back"[\s\S]*V20a2\.5 2\.5 0 0 1-2\.5 2\.5H12A2\.5 2\.5 0 0 1 9\.5 20z/,
    );
    assert.match(cssSource, /\.controls \.tab-ui-folder-icon\s*\{[\s\S]*stroke: #ffffff;/);
    assert.match(cssSource, /\.controls \.tab-ui-folder-icon-front\s*\{[\s\S]*fill: #000000;/);
    assert.match(
        cssSource,
        /body\.pref-show-tab-ui \.controls \.tab-ui-folder-icon\s*\{[\s\S]*opacity: 0\.78;/,
    );
});
