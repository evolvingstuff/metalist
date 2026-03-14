import assert from 'node:assert/strict';
import test from 'node:test';

import { buildNamespaceLoadingPageHtml } from '../../app/static/js/modules/modals/namespace-loading-page.js';


test('buildNamespaceLoadingPageHtml shows loading copy and wait cursor', () => {
    const html = buildNamespaceLoadingPageHtml('me');

    assert.match(html, /Loading namespace/);
    assert.match(html, /<div class="namespace-loading-namespace">me<\/div>/);
    assert.match(html, /cursor:\s*wait\s*!important;/);
    assert.match(html, /redirect automatically/);
});


test('buildNamespaceLoadingPageHtml escapes namespace text', () => {
    const html = buildNamespaceLoadingPageHtml('<script>alert(1)<\/script>');

    assert.doesNotMatch(html, /<script>alert\(1\)<\/script>/);
    assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
});
