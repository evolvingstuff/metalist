import assert from 'node:assert/strict';
import test from 'node:test';

import {
    blurFocusedSearchInput,
    focusSearchInputAndSelectAllText,
    resolveSearchInputDisplayQuery,
} from '../../app/static/js/modules/mode-manager/services/search-input-service.js';

test('untagged view visually hides the preserved tab query', () => {
    assert.equal(resolveSearchInputDisplayQuery('journal', true, false), '');
    assert.equal(resolveSearchInputDisplayQuery('journal', false, false), 'journal');
});

test('reference source view visually hides its internal UUID query', () => {
    assert.equal(
        resolveSearchInputDisplayQuery('f81d4fae-7dec-11d0-a765-00a0c91e6bf6', false, true),
        '',
    );
    assert.equal(resolveSearchInputDisplayQuery('journal', false, false), 'journal');
});

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

test('focusSearchInputAndSelectAllText focuses the search input and selects the full query', (t) => {
    const originalDocument = globalThis.document;

    const selectionCalls = [];
    const focusCalls = [];
    const searchInput = {
        value: 'project alpha',
        focus(options) {
            focusCalls.push(options);
        },
        setSelectionRange(start, end) {
            selectionCalls.push({ start, end });
        },
    };

    globalThis.document = {
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

    assert.equal(focusSearchInputAndSelectAllText(), true);
    assert.deepEqual(focusCalls, [{ preventScroll: true }]);
    assert.deepEqual(selectionCalls, [{ start: 0, end: 'project alpha'.length }]);
});

test('focusSearchInputAndSelectAllText is a no-op when search input is missing', (t) => {
    const originalDocument = globalThis.document;

    globalThis.document = {
        getElementById() {
            return null;
        },
    };

    t.after(() => {
        globalThis.document = originalDocument;
    });

    assert.equal(focusSearchInputAndSelectAllText(), false);
});
