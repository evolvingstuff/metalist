import assert from 'node:assert/strict';
import test from 'node:test';

import { buildContextMenuItems } from '../../app/static/js/modules/context-menu/context-menu-registry.js';

test('buildContextMenuItems returns note actions for note context', () => {
    const calls = [];
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123' },
        {
            onAddSiblingNote: (noteId) => calls.push(['addSibling', noteId]),
            onAddChildNote: (noteId) => calls.push(['addChild', noteId]),
            onDeleteNote: (noteId) => calls.push(['delete', noteId]),
            onMoveNoteToTop: (noteId) => calls.push(['moveToTop', noteId]),
        },
    );

    assert.deepEqual(
        items.map((item) => ({ id: item.id, label: item.label, enabled: item.enabled })),
        [
            { id: 'add-sibling-note', label: 'Add Sibling Note', enabled: true },
            { id: 'add-child-note', label: 'Add Child Note', enabled: true },
            { id: 'delete-note', label: 'Delete Note', enabled: true },
            { id: 'move-note-to-top', label: 'Move Note to Top', enabled: true },
        ],
    );

    for (const item of items) {
        item.onSelect();
    }

    assert.deepEqual(calls, [
        ['addSibling', 'note-123'],
        ['addChild', 'note-123'],
        ['delete', 'note-123'],
        ['moveToTop', 'note-123'],
    ]);
});

test('buildContextMenuItems preserves tag menu behavior', () => {
    const calls = [];
    const items = buildContextMenuItems(
        { kind: 'tag', tag: 'project-alpha', source: 'tag-bar' },
        {
            onEditTagRelationships: (tag) => calls.push(tag),
        },
    );

    assert.equal(items.length, 1);
    assert.equal(items[0].label, 'Edit Tag Relationships');

    items[0].onSelect();
    assert.deepEqual(calls, ['project-alpha']);
});
