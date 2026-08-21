import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildSearchSuggestionPresentation,
    buildSearchSuggestionWindowLabelMap,
    formatSearchSuggestionWindowLabel,
} from '../../app/static/js/modules/mode-manager/services/search-suggestion-window-labels-service.js';


test('search suggestion windows use concise human labels', () => {
    assert.equal(formatSearchSuggestionWindowLabel(1), 'today');
    assert.equal(formatSearchSuggestionWindowLabel(3), 'recent 3 days');
    assert.equal(formatSearchSuggestionWindowLabel(30), 'recent 30 days');
});


test('presentation labels only promoted suggestions and honors the UI toggle', () => {
    const suggestions = ['shortcut', 'short-story'];
    const personalized = [{ tag: 'shortcut', windowDays: 3 }];

    assert.deepEqual(
        buildSearchSuggestionPresentation(suggestions, personalized, true),
        [
            { tag: 'shortcut', windowLabel: 'recent 3 days' },
            { tag: 'short-story', windowLabel: '' },
        ],
    );
    assert.deepEqual(
        buildSearchSuggestionPresentation(suggestions, personalized, false),
        [
            { tag: 'shortcut', windowLabel: '' },
            { tag: 'short-story', windowLabel: '' },
        ],
    );
});


test('label map validates personalized suggestions against visible suggestions', () => {
    const labels = buildSearchSuggestionWindowLabelMap(
        ['shortcut', 'short-story'],
        [{ tag: 'shortcut', windowDays: 1 }],
    );

    assert.deepEqual(Array.from(labels.entries()), [['shortcut', 'today']]);
    assert.throws(
        () => buildSearchSuggestionWindowLabelMap(
            ['short-story'],
            [{ tag: 'shortcut', windowDays: 1 }],
        ),
        /must be visible/,
    );
});
