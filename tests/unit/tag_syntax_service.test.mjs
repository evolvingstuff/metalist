import assert from 'node:assert/strict';
import test from 'node:test';

import {
    analyzeTagBarInput,
    enforceTagBarInputForEditing,
    normalizeTagBarInput,
    parseTagBarSuggestionContext,
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

test('removes commas from tag tokens', () => {
    assert.equal(enforceTagBarInputForEditing('tag,-give'), 'tag-give');
});

test('preserves one trailing assignment separator while typing its value', () => {
    assert.equal(enforceTagBarInputForEditing('@size='), '@size=');
    assert.equal(enforceTagBarInputForEditing('{{@size='), '{{@size=');
    assert.equal(enforceTagBarInputForEditing('{{@size=2'), '{{@size=2');
    assert.equal(enforceTagBarInputForEditing('{{@size=2}}'), '{{@size=2}}');
    assert.equal(enforceTagBarInputForEditing('@size= '), '@size ');
    assert.equal(enforceTagBarInputForEditing('{{@size= }}'), '{{@size}}');
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

test('normalizeTagBarInput preserves one internal assignment separator for regular and meta tags', () => {
    assert.equal(normalizeTagBarInput('abc=2 abc=xyz {@size=1.25} @foo=bar'), 'abc=2 abc=xyz {@size=1.25} @foo=bar');
});

test('normalizeTagBarInput strips illegal assignment separators and invalid tag characters', () => {
    assert.equal(normalizeTagBarInput('a=b=c =abc abc='), 'abc abc abc');
    assert.equal(normalizeTagBarInput('abc=<script>'), 'abc=script');
});

test('exact uppercase OR is reserved and cannot be saved as a tag', () => {
    const reserved = analyzeTagBarInput('alpha OR beta');
    assert.equal(reserved.isValid, false);
    assert.equal(reserved.errorMessage, 'OR is reserved for search');

    const lowercase = analyzeTagBarInput('alpha or beta');
    assert.equal(lowercase.isValid, true);
    assert.equal(lowercase.normalizedText, 'alpha or beta');
});

test('parseTagBarSuggestionContext exposes all explicit tags including the current token', () => {
    const rawInput = 'linux Pandoc';
    const context = parseTagBarSuggestionContext(rawInput, rawInput.length);

    assert.deepEqual(context, {
        anchors: ['linux'],
        explicitTags: ['linux', 'Pandoc'],
        prefix: 'Pandoc',
        replaceStart: 6,
        replaceEnd: 12,
    });
});
