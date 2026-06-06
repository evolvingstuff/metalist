import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveNonContentNoteSelectionTarget } from '../../app/static/js/modules/mode-manager/services/note-click-target-service.js';

function createClosestTarget(lookups) {
    return {
        closest(selector) {
            if (!Object.prototype.hasOwnProperty.call(lookups, selector)) {
                return null;
            }
            return lookups[selector];
        },
    };
}

test('returns null for clicks inside note content', () => {
    const noteElement = { dataset: { noteId: 'parent-note' } };
    const noteContent = { className: 'note-content' };
    const target = createClosestTarget({
        '.note-content': noteContent,
        '.note': noteElement,
    });

    assert.equal(resolveNonContentNoteSelectionTarget(target), null);
});

test('returns null for clicks inside the editing tag bar', () => {
    const noteElement = { dataset: { noteId: 'parent-note' } };
    const tagBar = { className: 'note-tag-bar' };
    const target = createClosestTarget({
        '.note-content': null,
        '.note-tag-bar': tagBar,
        '.note': noteElement,
    });

    assert.equal(resolveNonContentNoteSelectionTarget(target), null);
});

test('returns null for clicks on the collapsed children indicator', () => {
    const noteElement = { dataset: { noteId: 'parent-note' } };
    const indicator = { className: 'note-collapsed-children-indicator' };
    const target = createClosestTarget({
        '.note-content': null,
        '.note-tag-bar': null,
        '.note-collapsed-children-indicator': indicator,
        '.note': noteElement,
    });

    assert.equal(resolveNonContentNoteSelectionTarget(target), null);
});

test('returns the parent note for clicks in parent-only whitespace', () => {
    const parentNote = { dataset: { noteId: 'parent-note' } };
    const noteChildren = { className: 'note-children' };
    const target = createClosestTarget({
        '.note-content': null,
        '.note': parentNote,
        '.note-children': noteChildren,
    });

    assert.equal(resolveNonContentNoteSelectionTarget(target), parentNote);
});

test('returns the nearest nested note for clicks on a child note shell', () => {
    const childNote = { dataset: { noteId: 'child-note' } };
    const target = createClosestTarget({
        '.note-content': null,
        '.note': childNote,
    });

    assert.equal(resolveNonContentNoteSelectionTarget(target), childNote);
});

test('returns null for targets without closest support', () => {
    assert.equal(resolveNonContentNoteSelectionTarget(null), null);
    assert.equal(resolveNonContentNoteSelectionTarget({}), null);
});
