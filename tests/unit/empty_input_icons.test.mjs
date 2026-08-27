import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const TEMPLATE_URL = new URL('../../app/templates/index.html', import.meta.url);
const TAG_BAR_SERVICE_URL = new URL(
    '../../app/static/js/modules/mode-manager/services/tag-bar-service.js',
    import.meta.url,
);
const CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);


test('search and tag inputs keep accessible grey icons and tooltips beside their text', async () => {
    const [templateSource, tagBarServiceSource, cssSource] = await Promise.all([
        readFile(TEMPLATE_URL, 'utf8'),
        readFile(TAG_BAR_SERVICE_URL, 'utf8'),
        readFile(CSS_URL, 'utf8'),
    ]);

    assert.match(
        templateSource,
        /id="search-input"[^>]*aria-label="Search notes"[^>]*title="Search"/,
    );
    assert.doesNotMatch(templateSource, /id="search-input"[^>]*placeholder=/);
    assert.match(templateSource, /class="search-input-empty-icon"/);
    assert.match(templateSource, /<circle[^>]*cx="11"[^>]*cy="11"[^>]*r="7"/);

    assert.doesNotMatch(tagBarServiceSource, /input\.placeholder\s*=/);
    assert.match(tagBarServiceSource, /input\.setAttribute\('aria-label', 'Tags'\);/);
    assert.match(tagBarServiceSource, /input\.setAttribute\('title', 'Tags'\);/);
    assert.match(tagBarServiceSource, /icon\.classList\.add\('note-tag-bar-empty-icon'\);/);
    assert.match(tagBarServiceSource, /icon\.setAttribute\('aria-hidden', 'true'\);/);
    assert.match(
        tagBarServiceSource,
        /backIconPath\.classList\.add\('note-tag-bar-empty-icon-back'\);/,
    );
    assert.match(
        tagBarServiceSource,
        /frontIconPath\.classList\.add\('note-tag-bar-empty-icon-front'\);/,
    );
    assert.match(tagBarServiceSource, /icon\.setAttribute\('viewBox', '0 0 16 16'\);/);
    assert.match(tagBarServiceSource, /backIconPath\.setAttribute\('d', tagPathData\);/);
    assert.match(tagBarServiceSource, /frontIconPath\.setAttribute\('d', tagPathData\);/);
    assert.match(
        tagBarServiceSource,
        /backIconPath\.setAttribute\('transform', 'translate\(4 0\)'\);/,
    );
    assert.match(tagBarServiceSource, /frontIconPath\.setAttribute\('fill-rule', 'evenodd'\);/);
    assert.match(tagBarServiceSource, /icon\.append\(backIconPath, frontIconPath\);/);

    assert.match(
        cssSource,
        /\.controls \.search-input\s*\{[\s\S]*padding: 0 12px 0 36px;/,
    );
    assert.match(
        cssSource,
        /\.note-tag-bar-input\s*\{[\s\S]*padding: 1px 2px 1px 22px;/,
    );
    assert.match(
        cssSource,
        /\.search-input-empty-icon,[\s\S]*\.note-tag-bar-empty-icon\s*\{[\s\S]*opacity: 1;[\s\S]*pointer-events: none;/,
    );
    assert.doesNotMatch(cssSource, /(?:search-input|note-tag-bar-input):placeholder-shown/);
    assert.match(
        cssSource,
        /\.note-tag-bar-empty-icon-back\s*\{[\s\S]*opacity: 0\.72;/,
    );
    assert.match(
        cssSource,
        /\.note-tag-bar-empty-icon\s*\{[\s\S]*overflow: visible;/,
    );
    assert.match(
        cssSource,
        /\.note-tag-bar-empty-icon-front\s*\{[\s\S]*fill: rgba\(245, 245, 245, 0\.95\);/,
    );
});
