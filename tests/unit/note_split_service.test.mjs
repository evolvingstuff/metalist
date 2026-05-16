import assert from 'node:assert/strict';
import test from 'node:test';

import { selectSplitSegmentHtmls } from '../../app/static/js/modules/mode-manager/services/note-split-service.js';

const textSegment = (html) => ({ html, hasText: true });
const blankSegment = () => ({ html: '', hasText: false });

test('caret split in the middle keeps before and after content', () => {
    const segments = selectSplitSegmentHtmls(
        [textSegment('foo'), textSegment('bar baz')],
        true,
    );

    assert.deepEqual(segments, ['foo', 'bar baz']);
});

test('caret split at the front creates a blank segment above', () => {
    const segments = selectSplitSegmentHtmls(
        [blankSegment(), textSegment('foo bar')],
        true,
    );

    assert.deepEqual(segments, ['', 'foo bar']);
});

test('caret split at the end creates a blank segment below', () => {
    const segments = selectSplitSegmentHtmls(
        [textSegment('foo bar'), blankSegment()],
        true,
    );

    assert.deepEqual(segments, ['foo bar', '']);
});

test('selection split in the middle keeps before selected and after content', () => {
    const segments = selectSplitSegmentHtmls(
        [textSegment('foo'), textSegment('bar'), textSegment('baz')],
        false,
    );

    assert.deepEqual(segments, ['foo', 'bar', 'baz']);
});

test('selection split touching the front creates a blank segment above', () => {
    const segments = selectSplitSegmentHtmls(
        [blankSegment(), textSegment('foo'), textSegment('bar')],
        false,
    );

    assert.deepEqual(segments, ['', 'foo', 'bar']);
});

test('selection split touching the end creates a blank segment below', () => {
    const segments = selectSplitSegmentHtmls(
        [textSegment('foo'), textSegment('bar'), blankSegment()],
        false,
    );

    assert.deepEqual(segments, ['foo', 'bar', '']);
});

test('selection split noops when the whole note is selected', () => {
    const segments = selectSplitSegmentHtmls(
        [blankSegment(), textSegment('foo bar'), blankSegment()],
        false,
    );

    assert.deepEqual(segments, []);
});
