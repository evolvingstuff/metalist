import assert from 'node:assert/strict';
import test from 'node:test';

import { buildContextMenuItems } from '../../app/static/js/modules/context-menu/context-menu-registry.js';

test('buildContextMenuItems returns note actions for note context', () => {
    const calls = [];
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123' },
        {
            onCopySelection: (noteId) => calls.push(['copySelection', noteId]),
            onCopyNote: (noteId) => calls.push(['copyNote', noteId]),
            onPasteNote: (noteId) => calls.push(['pasteNote', noteId]),
            onPasteNoteChild: (noteId) => calls.push(['pasteNoteChild', noteId]),
            onPasteReference: (noteId) => calls.push(['pasteReference', noteId]),
            onPasteReferenceChild: (noteId) => calls.push(['pasteReferenceChild', noteId]),
            onAddSiblingNote: (noteId) => calls.push(['addSibling', noteId]),
            onAddChildNote: (noteId) => calls.push(['addChild', noteId]),
            onDeleteNote: (noteId) => calls.push(['delete', noteId]),
            onMoveNoteToTop: (noteId) => calls.push(['moveToTop', noteId]),
        },
    );

    assert.deepEqual(
        items.map((item) => ({ id: item.id, label: item.label, enabled: item.enabled })),
        [
            { id: 'copy-note', label: 'Copy Note', enabled: true },
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
        ['copyNote', 'note-123'],
        ['addSibling', 'note-123'],
        ['addChild', 'note-123'],
        ['delete', 'note-123'],
        ['moveToTop', 'note-123'],
    ]);
});

test('buildContextMenuItems prepends image actions for note image context', () => {
    const calls = [];
    const imageContext = {
        sourceKind: 'inline',
        fileId: null,
        src: 'data:image/png;base64,AAAA',
        alt: 'Diagram',
        filename: null,
    };
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123', imageContext },
        {
            onCopySelection: (noteId) => calls.push(['copySelection', noteId]),
            onCopyNote: (noteId) => calls.push(['copyNote', noteId]),
            onPasteNote: (noteId) => calls.push(['pasteNote', noteId]),
            onPasteNoteChild: (noteId) => calls.push(['pasteNoteChild', noteId]),
            onPasteReference: (noteId) => calls.push(['pasteReference', noteId]),
            onPasteReferenceChild: (noteId) => calls.push(['pasteReferenceChild', noteId]),
            onCopyImage: (context) => calls.push(['copyImage', context]),
            onSaveImage: (context) => calls.push(['saveImage', context]),
            onZoomImage: (context) => calls.push(['zoomImage', context]),
            onOpenImageInNewTab: (context) => calls.push(['openImage', context]),
            onAddSiblingNote: (noteId) => calls.push(['addSibling', noteId]),
            onAddChildNote: (noteId) => calls.push(['addChild', noteId]),
            onDeleteNote: (noteId) => calls.push(['delete', noteId]),
            onMoveNoteToTop: (noteId) => calls.push(['moveToTop', noteId]),
        },
    );

    assert.deepEqual(
        items.map((item) => ({ id: item.id, label: item.label, enabled: item.enabled })),
        [
            { id: 'copy-image', label: 'Copy Image', enabled: true },
            { id: 'save-image', label: 'Save Image', enabled: true },
            { id: 'zoom-image', label: 'Zoom Image', enabled: true },
            { id: 'open-image-new-tab', label: 'Open Image in New Tab', enabled: true },
            { id: 'copy-note', label: 'Copy Note', enabled: true },
            { id: 'add-sibling-note', label: 'Add Sibling Note', enabled: true },
            { id: 'add-child-note', label: 'Add Child Note', enabled: true },
            { id: 'delete-note', label: 'Delete Note', enabled: true },
            { id: 'move-note-to-top', label: 'Move Note to Top', enabled: true },
        ],
    );
    assert.equal(items[4].separated, true);
    assert.equal(items[5].separated, undefined);

    items[0].onSelect();
    items[1].onSelect();
    items[2].onSelect();
    items[3].onSelect();

    assert.deepEqual(calls, [
        ['copyImage', imageContext],
        ['saveImage', imageContext],
        ['zoomImage', imageContext],
        ['openImage', imageContext],
    ]);
});

test('buildContextMenuItems shows text copy when selected text is present', () => {
    const calls = [];
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123', hasSelectedText: true },
        {
            onCopySelection: (noteId) => calls.push(['copySelection', noteId]),
            onCopyNote: (noteId) => calls.push(['copyNote', noteId]),
            onPasteNote: (noteId) => calls.push(['pasteNote', noteId]),
            onPasteNoteChild: (noteId) => calls.push(['pasteNoteChild', noteId]),
            onPasteReference: (noteId) => calls.push(['pasteReference', noteId]),
            onPasteReferenceChild: (noteId) => calls.push(['pasteReferenceChild', noteId]),
            onAddSiblingNote: (noteId) => calls.push(['addSibling', noteId]),
            onAddChildNote: (noteId) => calls.push(['addChild', noteId]),
            onDeleteNote: (noteId) => calls.push(['delete', noteId]),
            onMoveNoteToTop: (noteId) => calls.push(['moveToTop', noteId]),
        },
    );

    assert.equal(items[0].id, 'copy-selection');
    assert.equal(items[0].label, 'Copy');
    items[0].onSelect();
    assert.deepEqual(calls, [['copySelection', 'note-123']]);
});

test('buildContextMenuItems shows paste actions when note clipboard is available', () => {
    const calls = [];
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123', hasNoteClipboard: true },
        {
            onCopySelection: (noteId) => calls.push(['copySelection', noteId]),
            onCopyNote: (noteId) => calls.push(['copyNote', noteId]),
            onPasteNote: (noteId) => calls.push(['pasteNote', noteId]),
            onPasteNoteChild: (noteId) => calls.push(['pasteNoteChild', noteId]),
            onPasteReference: (noteId) => calls.push(['pasteReference', noteId]),
            onPasteReferenceChild: (noteId) => calls.push(['pasteReferenceChild', noteId]),
            onAddSiblingNote: (noteId) => calls.push(['addSibling', noteId]),
            onAddChildNote: (noteId) => calls.push(['addChild', noteId]),
            onDeleteNote: (noteId) => calls.push(['delete', noteId]),
            onMoveNoteToTop: (noteId) => calls.push(['moveToTop', noteId]),
        },
    );

    assert.deepEqual(
        items.slice(0, 5).map((item) => ({ id: item.id, label: item.label })),
        [
            { id: 'copy-note', label: 'Copy Note' },
            { id: 'paste-note', label: 'Paste Sibling Note' },
            { id: 'paste-note-child', label: 'Paste Child Note' },
            { id: 'paste-reference', label: 'Paste Sibling Reference' },
            { id: 'paste-reference-child', label: 'Paste Child Reference' },
        ],
    );

    items[1].onSelect();
    items[2].onSelect();
    items[3].onSelect();
    items[4].onSelect();
    assert.deepEqual(calls, [
        ['pasteNote', 'note-123'],
        ['pasteNoteChild', 'note-123'],
        ['pasteReference', 'note-123'],
        ['pasteReferenceChild', 'note-123'],
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
