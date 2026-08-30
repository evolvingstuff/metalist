import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const TEMPLATE_URL = new URL('../../app/templates/index.html', import.meta.url);
const CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);
const COMMAND_PALETTE_CONTROLLER_URL = new URL(
    '../../app/static/js/modules/command-palette/command-palette-controller.js',
    import.meta.url,
);


test('enabled tabs expose a white outline folder indicator inside the hover trigger', async () => {
    const [templateSource, cssSource, commandPaletteControllerSource] = await Promise.all([
        readFile(TEMPLATE_URL, 'utf8'),
        readFile(CSS_URL, 'utf8'),
        readFile(COMMAND_PALETTE_CONTROLLER_URL, 'utf8'),
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
    assert.match(
        cssSource,
        /\.controls \.tab-ui-folder-icon\s*\{[\s\S]*left: 6px;[\s\S]*transform: translateY\(-50%\);/,
    );
    assert.match(
        cssSource,
        /\.controls \.search-results-count\s*\{[\s\S]*right: 6px;/,
    );
    assert.match(
        templateSource,
        /search-results-root-count">0 roots<\/span>[\s\S]*search-results-token-count">≈ 0 tokens<\/span>/,
    );
    assert.match(
        cssSource,
        /\.controls \.search-results-count\s*\{[\s\S]*flex-direction: column;[\s\S]*align-items: flex-end;/,
    );
    assert.match(
        cssSource,
        /\.controls \.search-controls\s*\{[\s\S]*--search-input-width:\s*clamp\(140px, calc\(100% - 184px\), 500px\);[\s\S]*--search-input-half-width:\s*clamp\(70px, calc\(50% - 92px\), 250px\);/,
    );
    assert.doesNotMatch(
        cssSource,
        /@container search-shell \(max-width: 440px\)\s*\{[\s\S]*?\.controls \.search-results-count\s*\{[\s\S]*?display:\s*none;/,
    );
    assert.match(
        cssSource,
        /body:not\(\.pref-show-search-results-count\) \.controls \.search-results-count\s*\{[\s\S]*?display:\s*none;/,
    );
    assert.match(
        commandPaletteControllerSource,
        /'pref\.show_search_results_count',[\s\S]*?true,[\s\S]*?'pref-show-search-results-count'/,
    );
    assert.match(cssSource, /\.controls \.tab-ui-folder-icon-front\s*\{[\s\S]*fill: #000000;/);
    assert.match(
        cssSource,
        /body\.pref-show-tab-ui \.controls \.tab-ui-folder-icon\s*\{[\s\S]*opacity: 0\.78;/,
    );
});
