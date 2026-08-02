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
    });
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


test('applyNoteLayoutSettings exposes all three presets to CSS', () => {
    const attributes = new Map();
    const body = {
        setAttribute: (name, value) => attributes.set(name, value),
    };
    const settings = {
        topLevelNoteSize: 'largest',
        childIndentation: 'wide',
        verticalSpacing: 'spacious',
    };

    applyNoteLayoutSettings(body, settings);

    assert.equal(attributes.get('data-top-level-note-size'), 'largest');
    assert.equal(attributes.get('data-child-indentation'), 'wide');
    assert.equal(attributes.get('data-note-vertical-spacing'), 'spacious');
});
