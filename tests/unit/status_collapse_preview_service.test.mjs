import assert from 'node:assert/strict';
import test from 'node:test';

import { extractCollapsedStatusPreviewFromHtml } from '../../app/static/js/modules/mode-manager/services/status-collapse-preview-service.js';

test('extractCollapsedStatusPreviewFromHtml keeps single-line status notes uncollapsed', () => {
    const preview = extractCollapsedStatusPreviewFromHtml('foo');

    assert.deepEqual(preview, {
        previewText: 'foo',
        hasAdditionalLines: false,
    });
});

test('extractCollapsedStatusPreviewFromHtml uses the first block line as the collapsed preview', () => {
    const preview = extractCollapsedStatusPreviewFromHtml('<div>foo</div><div>bar</div>');

    assert.deepEqual(preview, {
        previewText: 'foo',
        hasAdditionalLines: true,
    });
});

test('extractCollapsedStatusPreviewFromHtml treats block openings as line boundaries', () => {
    const preview = extractCollapsedStatusPreviewFromHtml('foo<div>bar</div>');

    assert.deepEqual(preview, {
        previewText: 'foo',
        hasAdditionalLines: true,
    });
});

test('extractCollapsedStatusPreviewFromHtml handles nested block wrappers from contenteditable HTML', () => {
    const preview = extractCollapsedStatusPreviewFromHtml('<div>foo<div>bar</div></div>');

    assert.deepEqual(preview, {
        previewText: 'foo',
        hasAdditionalLines: true,
    });
});

test('extractCollapsedStatusPreviewFromHtml treats br tags as line boundaries', () => {
    const preview = extractCollapsedStatusPreviewFromHtml('foo<br>bar');

    assert.deepEqual(preview, {
        previewText: 'foo',
        hasAdditionalLines: true,
    });
});

test('extractCollapsedStatusPreviewFromHtml skips blank lines and decodes basic entities', () => {
    const preview = extractCollapsedStatusPreviewFromHtml('<div>&nbsp;</div><div>foo &amp; bar</div><div>baz</div>');

    assert.deepEqual(preview, {
        previewText: 'foo & bar',
        hasAdditionalLines: true,
    });
});
