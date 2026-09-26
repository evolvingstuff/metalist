import assert from 'node:assert/strict';
import test from 'node:test';

import {
    DEFAULT_NOTE_LAYOUT_SETTINGS,
    NOTE_LAYOUT_OPTIONS,
    applyNoteLayoutSettings,
    validateNoteLayoutSettings,
} from '../../app/static/js/modules/command-palette/note-layout-preferences.js';


test('note layout defaults preserve the existing indentation and spacing while enlarging roots', () => {
    assert.deepEqual(DEFAULT_NOTE_LAYOUT_SETTINGS, {
        topLevelNoteSize: 'larger',
        childIndentation: 'standard',
        verticalSpacing: 'comfortable',
        noteCorners: 'round',
        tagStyle: 'pills',
    });
});


test('corner and tag style presets use clear labels', () => {
    assert.deepEqual(
        NOTE_LAYOUT_OPTIONS.noteCorners.map((option) => [option.value, option.label]),
        [['subtle', 'Subtle'], ['rounded', 'Rounded'], ['round', 'Round']],
    );
    assert.deepEqual(
        NOTE_LAYOUT_OPTIONS.tagStyle.map((option) => [option.value, option.label]),
        [['pills', 'Pills'], ['text', 'Plain text']],
    );
});


test('validateNoteLayoutSettings rejects an unknown tag style', () => {
    assert.throws(
        () => validateNoteLayoutSettings({
            ...DEFAULT_NOTE_LAYOUT_SETTINGS,
            tagStyle: 'bubbles',
        }),
        /tagStyle/,
    );
});


test('top-level size presets use clear progressive labels', () => {
    assert.deepEqual(
        NOTE_LAYOUT_OPTIONS.topLevelNoteSize.map((option) => option.label),
        ['Same as children', 'Larger', 'Even larger'],
    );
});


test('validateNoteLayoutSettings rejects unknown preset values', () => {
    assert.throws(
        () => validateNoteLayoutSettings({
            topLevelNoteSize: 'huge',
            childIndentation: 'standard',
            verticalSpacing: 'comfortable',
        }),
        /topLevelNoteSize/,
    );
});


test('applyNoteLayoutSettings exposes every preset to CSS', () => {
    const attributes = new Map();
    const body = {
        setAttribute: (name, value) => attributes.set(name, value),
    };
    const settings = {
        topLevelNoteSize: 'largest',
        childIndentation: 'wide',
        verticalSpacing: 'spacious',
        noteCorners: 'subtle',
        tagStyle: 'text',
    };

    applyNoteLayoutSettings(body, settings);

    assert.equal(attributes.get('data-top-level-note-size'), 'largest');
    assert.equal(attributes.get('data-child-indentation'), 'wide');
    assert.equal(attributes.get('data-note-vertical-spacing'), 'spacious');
    assert.equal(attributes.get('data-note-corners'), 'subtle');
    assert.equal(attributes.get('data-tag-style'), 'text');
});
