import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldCreateTopNoteForFileDrop } from '../../app/static/js/modules/mode-manager/services/file-drop-policy-service.js';

test('keeps a dropped PDF in the active editing note when pointer hit-testing misses its content', () => {
    const shouldCreateTopNote = shouldCreateTopNoteForFileDrop({
        isEditing: true,
        currentNoteId: 'new-note',
        hasNonImageFile: true,
        hasEditingDropTarget: false,
    });

    assert.equal(shouldCreateTopNote, false);
});

test('creates a top note for a dropped file when no note is being edited', () => {
    const shouldCreateTopNote = shouldCreateTopNoteForFileDrop({
        isEditing: false,
        currentNoteId: null,
        hasNonImageFile: true,
        hasEditingDropTarget: false,
    });

    assert.equal(shouldCreateTopNote, true);
});

test('rejects editing state without a current note id', () => {
    assert.throws(
        () => shouldCreateTopNoteForFileDrop({
            isEditing: true,
            currentNoteId: null,
            hasNonImageFile: true,
            hasEditingDropTarget: false,
        }),
        /requires currentNoteId while editing/,
    );
});

test('preserves top-note creation for an image-only drop outside the active editor', () => {
    const shouldCreateTopNote = shouldCreateTopNoteForFileDrop({
        isEditing: true,
        currentNoteId: 'new-note',
        hasNonImageFile: false,
        hasEditingDropTarget: false,
    });

    assert.equal(shouldCreateTopNote, true);
});
