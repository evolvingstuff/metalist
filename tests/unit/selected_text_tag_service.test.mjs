import assert from 'node:assert/strict';
import test from 'node:test';

import {
    MAX_SELECTED_TEXT_TAG_CHARACTERS,
    normalizeSelectedTextForTagAction,
} from '../../app/static/js/modules/mode-manager/services/selected-text-tag-service.js';


test('normalizeSelectedTextForTagAction trims and collapses selected whitespace', () => {
    assert.equal(normalizeSelectedTextForTagAction('  Neural\nNetworks  '), 'Neural Networks');
});


test('normalizeSelectedTextForTagAction rejects selections over the limit', () => {
    assert.equal(MAX_SELECTED_TEXT_TAG_CHARACTERS, 25);
    assert.equal(normalizeSelectedTextForTagAction('a'.repeat(26)), null);
});


test('normalizeSelectedTextForTagAction rejects text with no usable tag characters', () => {
    assert.equal(normalizeSelectedTextForTagAction('<<<>>>'), null);
});


test('normalizeSelectedTextForTagAction rejects exact uppercase OR only', () => {
    assert.equal(normalizeSelectedTextForTagAction('OR'), null);
    assert.equal(normalizeSelectedTextForTagAction('or'), 'or');
});
