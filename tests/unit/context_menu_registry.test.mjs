import assert from 'node:assert/strict';
import test from 'node:test';

import { buildContextMenuItems } from '../../app/static/js/modules/context-menu/context-menu-registry.js';

function buildNoteHandlers(calls) {
    return {
        onCopySelection: (noteId) => calls.push(['copySelection', noteId]),
        onCopyNote: (noteId) => calls.push(['copyNote', noteId]),
        onPasteNote: (noteId) => calls.push(['pasteNote', noteId]),
        onPasteNoteChild: (noteId) => calls.push(['pasteNoteChild', noteId]),
        onPasteReference: (noteId) => calls.push(['pasteReference', noteId]),
        onPasteReferenceChild: (noteId) => calls.push(['pasteReferenceChild', noteId]),
        onExportNoteHtml: (noteId) => calls.push(['exportNoteHtml', noteId]),
        onExportViewHtml: () => calls.push(['exportViewHtml']),
        onAddSiblingNote: (noteId) => calls.push(['addSibling', noteId]),
        onAddChildNote: (noteId) => calls.push(['addChild', noteId]),
        onDeleteNote: (noteId) => calls.push(['delete', noteId]),
        onMoveNoteToTop: (noteId) => calls.push(['moveToTop', noteId]),
    };
}

test('buildContextMenuItems returns note actions for note context', () => {
    const calls = [];
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123' },
        buildNoteHandlers(calls),
    );

    assert.deepEqual(
        items.map((item) => ({ id: item.id, label: item.label, enabled: item.enabled })),
        [
            { id: 'copy-note', label: 'Copy Note', enabled: true },
            { id: 'add-sibling-note', label: 'Add Sibling Note', enabled: true },
            { id: 'add-child-note', label: 'Add Child Note', enabled: true },
            { id: 'delete-note', label: 'Delete Note', enabled: true },
            { id: 'move-note-to-top', label: 'Move Note to Top', enabled: true },
            { id: 'export-note-html', label: 'Export Note as HTML', enabled: true },
            { id: 'export-view-html', label: 'Export View as HTML', enabled: true },
        ],
    );
    assert.equal(items[0].separated, undefined);
    assert.equal(items[5].separated, true);

    for (const item of items) {
        item.onSelect();
    }

    assert.deepEqual(calls, [
        ['copyNote', 'note-123'],
        ['addSibling', 'note-123'],
        ['addChild', 'note-123'],
        ['delete', 'note-123'],
        ['moveToTop', 'note-123'],
        ['exportNoteHtml', 'note-123'],
        ['exportViewHtml'],
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
            ...buildNoteHandlers(calls),
            onCopyImage: (context) => calls.push(['copyImage', context]),
            onSaveImage: (context) => calls.push(['saveImage', context]),
            onZoomImage: (context) => calls.push(['zoomImage', context]),
            onOpenImageInNewTab: (context) => calls.push(['openImage', context]),
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
            { id: 'export-note-html', label: 'Export Note as HTML', enabled: true },
            { id: 'export-view-html', label: 'Export View as HTML', enabled: true },
        ],
    );
    assert.equal(items[4].separated, true);
    assert.equal(items[5].separated, undefined);
    assert.equal(items[9].separated, true);

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
        buildNoteHandlers(calls),
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
        buildNoteHandlers(calls),
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
    assert.deepEqual(
        items.slice(-2).map((item) => ({ id: item.id, label: item.label })),
        [
            { id: 'export-note-html', label: 'Export Note as HTML' },
            { id: 'export-view-html', label: 'Export View as HTML' },
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

test('buildContextMenuItems returns export view for view context', () => {
    const calls = [];
    const items = buildContextMenuItems(
        { kind: 'view' },
        {
            onExportViewHtml: () => calls.push(['exportViewHtml']),
        },
    );

    assert.deepEqual(
        items.map((item) => ({ id: item.id, label: item.label, enabled: item.enabled })),
        [
            { id: 'export-view-html', label: 'Export View as HTML', enabled: true },
        ],
    );

    items[0].onSelect();
    assert.deepEqual(calls, [['exportViewHtml']]);
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
