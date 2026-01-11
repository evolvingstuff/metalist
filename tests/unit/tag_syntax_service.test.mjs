import assert from 'node:assert/strict';
import test from 'node:test';

import {
    analyzeTagBarInput,
    enforceTagBarInputForEditing,
    normalizeTagBarInput,
} from '../../app/static/js/modules/mode-manager/services/tag-syntax-service.js';

test('allows matching bracket wrappers up to 3', () => {
    assert.equal(enforceTagBarInputForEditing('[tag]'), '[tag]');
    assert.equal(enforceTagBarInputForEditing('((tag))'), '((tag))');
    assert.equal(enforceTagBarInputForEditing('{{{tag}}}'), '{{{tag}}}');
});

test('truncates wrappers beyond 3', () => {
    assert.equal(enforceTagBarInputForEditing('((((tag))))'), '(((tag)))');
    assert.equal(enforceTagBarInputForEditing('[[[[tag]]]]'), '[[[tag]]]');
    assert.equal(enforceTagBarInputForEditing('{{{{tag}}}}'), '{{{tag}}}');
});

test('autocorrects mismatched or extra wrapper closers', () => {
    assert.equal(enforceTagBarInputForEditing('[tag)'), '[tag');
    assert.equal(enforceTagBarInputForEditing('tag]'), 'tag');
    assert.equal(enforceTagBarInputForEditing('[tag]]'), '[tag]');
    assert.equal(enforceTagBarInputForEditing('((tag))}'), '((tag))');
});

test('preserves standalone / tokens while editing (comment start)', () => {
    assert.equal(enforceTagBarInputForEditing('foo bar /'), 'foo bar /');
    assert.equal(enforceTagBarInputForEditing('foo bar / '), 'foo bar / ');
});

test('does not warn on bare wrapper openers (but omits from sanitizedText)', () => {
    const analysis = analyzeTagBarInput('(');
    assert.equal(analysis.isValid, true);
    assert.equal(analysis.errorMessage, null);
    assert.equal(analysis.sanitizedText, '');
    assert.equal(analysis.normalizedText, '(');
});

test('warns on unclosed wrapper state after content and omits from sanitizedText', () => {
    const analysis = analyzeTagBarInput('foo (bar');
    assert.equal(analysis.isValid, false);
    assert.equal(analysis.errorMessage, 'Close tag wrapper with )');
    assert.equal(analysis.sanitizedText, 'foo');
    assert.equal(analysis.normalizedText, 'foo (bar');
});

test('does not warn on empty unclosed comment start (but omits from sanitizedText)', () => {
    const analysis = analyzeTagBarInput('foo /*');
    assert.equal(analysis.isValid, true);
    assert.equal(analysis.errorMessage, null);
    assert.equal(analysis.sanitizedText, 'foo');
    assert.equal(analysis.normalizedText, 'foo /*');
});

test('warns on unclosed comments with content and preserves normalizedText', () => {
    const analysis = analyzeTagBarInput('foo /*bar');
    assert.equal(analysis.isValid, false);
    assert.equal(analysis.errorMessage, 'Close comment with */');
    assert.equal(analysis.sanitizedText, 'foo');
    assert.equal(analysis.normalizedText, 'foo /*bar');
});

test('normalizeTagBarInput preserves closed wrappers', () => {
    assert.equal(normalizeTagBarInput(' [tag]  '), '[tag]');
    assert.equal(normalizeTagBarInput('((tag))   {{{tag}}}'), '((tag)) {{{tag}}}');
});
