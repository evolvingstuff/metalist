import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldFocusSearchInputForViewModeTab } from '../../app/static/js/modules/mode-manager/services/view-mode-search-shortcut-service.js';

function viewModeTabOptions(overrides) {
    return {
        key: 'Tab',
        shiftKey: false,
        altKey: false,
        metaKey: false,
        ctrlKey: false,
        isEditing: false,
        isSearching: false,
        isLoading: false,
        modalStack: [],
        ...overrides,
    };
}

test('plain Tab focuses search input in view mode', () => {
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({})), true);
});

test('view-mode search Tab shortcut ignores modified Tab', () => {
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({ shiftKey: true })), false);
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({ altKey: true })), false);
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({ metaKey: true })), false);
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({ ctrlKey: true })), false);
});

test('view-mode search Tab shortcut is disabled outside view mode', () => {
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({ isEditing: true })), false);
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({ isSearching: true })), false);
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({ isLoading: true })), false);
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({ modalStack: ['helpModal'] })), false);
});

test('view-mode search shortcut ignores non-Tab keys', () => {
    assert.equal(shouldFocusSearchInputForViewModeTab(viewModeTabOptions({ key: 'Enter' })), false);
});
