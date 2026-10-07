import assert from 'node:assert/strict';
import test from 'node:test';

import {
    DEFAULT_DICTATION_TAG_PHRASE,
    isValidDictationTagPhrase,
    splitDictatedNotePaste,
} from '../../app/static/js/modules/mode-manager/services/dictation-note-paste.js';

// Dictated text pasted into a note: what follows the tag phrase ("start tags" by
// default) becomes tags (docs/ui/dictation-paste.md).

test('the text before the phrase is content, the text after it is tags', () => {
    assert.deepEqual(splitDictatedNotePaste('Here is my content start tags foo bar', 'start tags'),
        { content: 'Here is my content', tagText: 'foo bar' });
});

test('Superwhisper punctuation and capitals around and inside the phrase', () => {
    assert.deepEqual(splitDictatedNotePaste('Here is my content. Start tags. Neural network, python.', 'start tags'),
        { content: 'Here is my content.', tagText: 'Neural network, python.' });
    assert.deepEqual(splitDictatedNotePaste('Here is my content, start, tags: foo', 'start tags'),
        { content: 'Here is my content', tagText: 'foo' });
    assert.deepEqual(splitDictatedNotePaste('Is it done? START TAGS foo', 'start tags'),
        { content: 'Is it done?', tagText: 'foo' });
});

test('only tags, or only content before the phrase', () => {
    // Dictating only tags into the note being edited.
    assert.deepEqual(splitDictatedNotePaste('Start tags, scratch pad.', 'start tags'),
        { content: '', tagText: 'scratch pad.' });
    assert.deepEqual(splitDictatedNotePaste('Start tags neural network', 'start tags'),
        { content: '', tagText: 'neural network' });
    assert.deepEqual(splitDictatedNotePaste('Here is my content start tags', 'start tags'),
        { content: 'Here is my content', tagText: '' });
});

test('without the phrase the paste is not dictation', () => {
    assert.equal(splitDictatedNotePaste('The paper about neural networks', 'start tags'), null);
    // Part of the phrase, the words apart, or inside other words, it is ordinary text.
    assert.equal(splitDictatedNotePaste('Start the tags later', 'start tags'), null);
    assert.equal(splitDictatedNotePaste('restart tags foo', 'start tags'), null);
    assert.equal(splitDictatedNotePaste('start tagsfoo', 'start tags'), null);
});

test('only the first phrase counts; later ones are dropped from the tags', () => {
    assert.deepEqual(splitDictatedNotePaste('Content start tags foo start tags bar', 'start tags'),
        { content: 'Content', tagText: 'foo bar' });
});

test('the phrase is configurable, from one unusual word to several words', () => {
    assert.deepEqual(splitDictatedNotePaste('Content. Armadillo. foo', 'armadillo'),
        { content: 'Content.', tagText: 'foo' });
    assert.deepEqual(splitDictatedNotePaste('Content now add these tags foo', 'now add these tags'),
        { content: 'Content', tagText: 'foo' });
    assert.equal(splitDictatedNotePaste('Content start tags foo', 'armadillo'), null);
});

test('a phrase is words of letters, start tags by default', () => {
    assert.equal(DEFAULT_DICTATION_TAG_PHRASE, 'start tags');
    assert.deepEqual(splitDictatedNotePaste('Here is my content. Start tags. foo bar', DEFAULT_DICTATION_TAG_PHRASE),
        { content: 'Here is my content.', tagText: 'foo bar' });
    for (const phrase of ['start tags', 'Armadillo', 'now add these tags']) assert.equal(isValidDictationTagPhrase(phrase), true);
    for (const phrase of ['', 'a', 'start  tags', ' start tags', 'tags1', 'start-tags', 'a'.repeat(65)]) {
        assert.equal(isValidDictationTagPhrase(phrase), false, phrase);
    }
    assert.throws(() => splitDictatedNotePaste('Content start tags foo', 'start-tags'));
});
