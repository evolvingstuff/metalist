import assert from 'node:assert/strict';
import test from 'node:test';

import { blurFocusedSearchInput } from '../../app/static/js/modules/mode-manager/services/search-input-service.js';

test('blurFocusedSearchInput blurs the active search input', (t) => {
    const originalDocument = globalThis.document;

    let blurCount = 0;
    const searchInput = {
        blur() {
            blurCount += 1;
        },
    };

    globalThis.document = {
        activeElement: searchInput,
        getElementById(id) {
            if (id === 'search-input') {
                return searchInput;
            }
            return null;
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
    });

    assert.equal(blurFocusedSearchInput(), true);
    assert.equal(blurCount, 1);
});

test('blurFocusedSearchInput is a no-op when search input is not focused', (t) => {
    const originalDocument = globalThis.document;

    let blurCount = 0;
    const searchInput = {
        blur() {
            blurCount += 1;
        },
    };

    globalThis.document = {
        activeElement: {},
        getElementById(id) {
            if (id === 'search-input') {
                return searchInput;
            }
            return null;
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
    });

    assert.equal(blurFocusedSearchInput(), false);
    assert.equal(blurCount, 0);
});
