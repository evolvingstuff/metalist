import assert from 'node:assert/strict';
import test from 'node:test';

import {
    analyzeSearchQueryInput,
    findSearchTagAtIndex,
} from '../../app/static/js/modules/mode-manager/services/search-syntax-service.js';

test('uppercase OR separates complete implicit-AND clauses', () => {
    const analysis = analyzeSearchQueryInput('A B C OR D E OR "some text"');

    assert.equal(analysis.isComplete, true);
    assert.equal(analysis.warningMessage, null);
    assert.equal(analysis.normalizedText, 'A B C OR D E OR "some text"');
    assert.equal(analysis.sanitizedText, 'A B C OR D E OR "some text"');
});

test('leading trailing and consecutive OR operators are incomplete', () => {
    for (const query of ['OR A', 'A OR', 'A OR OR B']) {
        const analysis = analyzeSearchQueryInput(query);
        assert.equal(analysis.isComplete, false, query);
        assert.match(analysis.warningMessage, /OR/);
    }
});

test('lowercase or and quoted OR remain searchable terms', () => {
    assert.equal(analyzeSearchQueryInput('or').isComplete, true);
    assert.equal(analyzeSearchQueryInput('"OR"').isComplete, true);
});

test('a tag token normalized to uppercase OR is rejected as reserved', () => {
    const analysis = analyzeSearchQueryInput('A OR:');

    assert.equal(analysis.isComplete, false);
    assert.match(analysis.warningMessage, /reserved/);
    assert.equal(analysis.sanitizedText, 'A');
});

test('OR operator is not exposed as a tag suggestion target', () => {
    assert.equal(findSearchTagAtIndex('A OR B', 3), null);
    assert.deepEqual(findSearchTagAtIndex('A OR B', 6), {
        tag: 'B',
        start: 5,
        end: 6,
        prefix: null,
    });
});
