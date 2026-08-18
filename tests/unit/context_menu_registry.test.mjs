import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { buildContextMenuItems } from '../../app/static/js/modules/context-menu/context-menu-registry.js';
import { isContextMenuIconSupported } from '../../app/static/js/modules/context-menu/context-menu-service.js';

const CONTEXT_MENU_EVENTS_URL = new URL(
    '../../app/static/js/modules/mode-manager/events/context-menu-events.js',
    import.meta.url,
);

function buildNoteHandlers(calls) {
    return {
        onCopySelection: (noteId) => calls.push(['copySelection', noteId]),
        onAddSelectionAsTag: (noteId, selectedText) => calls.push(['addSelectionAsTag', noteId, selectedText]),
        onAddStyle: (noteId, styleTag) => calls.push(['addStyle', noteId, styleTag]),
        onRemoveFormatting: (noteId) => calls.push(['removeFormatting', noteId]),
        onCopyNote: (noteId) => calls.push(['copyNote', noteId]),
        onPasteNote: (noteId) => calls.push(['pasteNote', noteId]),
        onPasteNoteChild: (noteId) => calls.push(['pasteNoteChild', noteId]),
        onPasteReference: (noteId) => calls.push(['pasteReference', noteId]),
        onPasteReferenceChild: (noteId) => calls.push(['pasteReferenceChild', noteId]),
        onOpenReferenceSource: (referenceNoteId) => calls.push(['openReferenceSource', referenceNoteId]),
        onMakeImageBigger: (context) => calls.push(['makeImageBigger', context]),
        onMakeImageSmaller: (context) => calls.push(['makeImageSmaller', context]),
        onResetImageSize: (context) => calls.push(['resetImageSize', context]),
        onExportNoteHtml: (noteId) => calls.push(['exportNoteHtml', noteId]),
        onExportViewHtml: () => calls.push(['exportViewHtml']),
        onViewNoteFullscreen: (noteId) => calls.push(['viewNoteFullscreen', noteId]),
        onAddNoteAtTop: () => calls.push(['addNoteAtTop']),
        onAddSiblingNote: (noteId) => calls.push(['addSibling', noteId]),
        onAddChildNote: (noteId) => calls.push(['addChild', noteId]),
        onDeleteNote: (noteId) => calls.push(['delete', noteId]),
        onMoveNoteToTop: (noteId) => calls.push(['moveToTop', noteId]),
    };
}

test('buildContextMenuItems prepends source action for a reference context', () => {
    const calls = [];
    const items = buildContextMenuItems(
        {
            kind: 'note',
            noteId: 'host-note-123',
            referenceNoteId: 'source-note-456',
        },
        buildNoteHandlers(calls),
    );

    assert.deepEqual(
        {
            id: items[0].id,
            label: items[0].label,
            icon: items[0].icon,
            enabled: items[0].enabled,
        },
        {
            id: 'open-reference-source',
            label: 'Go to Source',
            icon: 'external',
            enabled: true,
        },
    );
    assert.equal(items[1].separated, true);

    items[0].onSelect();
    assert.deepEqual(calls, [['openReferenceSource', 'source-note-456']]);
});

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

test('buildContextMenuItems exposes full screen only for an eligible view-mode note', () => {
    const calls = [];
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123', canViewFullscreen: true },
        buildNoteHandlers(calls),
    );

    const fullscreenItem = items.find((item) => item.id === 'view-note-fullscreen');
    assert.ok(fullscreenItem);
    assert.equal(fullscreenItem.label, 'View Full Screen');
    assert.equal(isContextMenuIconSupported(fullscreenItem.icon), true);
    fullscreenItem.onSelect();
    assert.deepEqual(calls, [['viewNoteFullscreen', 'note-123']]);

    const editingItems = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123', canViewFullscreen: false },
        buildNoteHandlers([]),
    );
    assert.equal(editingItems.some((item) => item.id === 'view-note-fullscreen'), false);
});

test('buildContextMenuItems prepends image actions for note image context', () => {
    const calls = [];
    const imageContext = {
        sourceKind: 'inline',
        fileId: null,
        hostNoteId: 'note-123',
        occurrenceIndex: 0,
        src: 'data:image/png;base64,AAAA',
        alt: 'Diagram',
        filename: null,
    };
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123', imageContext, canResizeImage: true },
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
            { id: 'make-image-bigger', label: 'Make Bigger', enabled: true },
            { id: 'make-image-smaller', label: 'Make Smaller', enabled: true },
            { id: 'reset-image-size', label: 'Reset Size', enabled: true },
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
    assert.equal(items[3].separated, true);
    assert.equal(items[7].separated, true);
    assert.equal(items[8].separated, undefined);
    assert.equal(items[12].separated, true);

    for (const item of items) {
        if (typeof item.icon === 'string') {
            assert.equal(isContextMenuIconSupported(item.icon), true, `unsupported icon: ${item.icon}`);
        }
    }

    items[0].onSelect();
    items[1].onSelect();
    items[2].onSelect();
    items[3].onSelect();
    items[4].onSelect();
    items[5].onSelect();
    items[6].onSelect();

    assert.deepEqual(calls, [
        ['makeImageBigger', imageContext],
        ['makeImageSmaller', imageContext],
        ['resetImageSize', imageContext],
        ['copyImage', imageContext],
        ['saveImage', imageContext],
        ['zoomImage', imageContext],
        ['openImage', imageContext],
    ]);
});

test('buildContextMenuItems hides image sizing actions while editing', () => {
    const calls = [];
    const imageContext = {
        sourceKind: 'inline',
        fileId: null,
        hostNoteId: 'note-123',
        occurrenceIndex: 0,
        src: 'data:image/png;base64,AAAA',
        alt: 'Diagram',
        filename: null,
    };
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123', imageContext, canResizeImage: false },
        {
            ...buildNoteHandlers(calls),
            onCopyImage: (context) => calls.push(['copyImage', context]),
            onSaveImage: (context) => calls.push(['saveImage', context]),
            onZoomImage: (context) => calls.push(['zoomImage', context]),
            onOpenImageInNewTab: (context) => calls.push(['openImage', context]),
        },
    );

    assert.equal(items.some((item) => item.id === 'make-image-bigger'), false);
    assert.equal(items.some((item) => item.id === 'make-image-smaller'), false);
    assert.equal(items.some((item) => item.id === 'reset-image-size'), false);
    assert.deepEqual(items.slice(0, 4).map((item) => item.id), [
        'copy-image',
        'save-image',
        'zoom-image',
        'open-image-new-tab',
    ]);
    assert.equal(items[0].separated, undefined);
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

test('buildContextMenuItems shows add-as-tag for an eligible text selection', () => {
    const calls = [];
    const items = buildContextMenuItems(
        {
            kind: 'note',
            noteId: 'note-123',
            hasSelectedText: true,
            selectedTextForTag: 'Neural Networks',
        },
        buildNoteHandlers(calls),
    );

    assert.deepEqual(
        items.slice(0, 2).map((item) => ({ id: item.id, label: item.label })),
        [
            { id: 'copy-selection', label: 'Copy' },
            { id: 'add-selection-as-tag', label: 'Add as Tag' },
        ],
    );
    items[1].onSelect();
    assert.deepEqual(calls, [['addSelectionAsTag', 'note-123', 'Neural Networks']]);
});

test('buildContextMenuItems adds a connected Add Style submenu only for the editing note', () => {
    const calls = [];
    const items = buildContextMenuItems(
        {
            kind: 'note',
            noteId: 'note-123',
            canAddStyle: true,
            styleOptions: [
                { id: 'red', label: 'Red', tag: '@red' },
                { id: 'markdown', label: 'Markdown', tag: '@markdown' },
            ],
        },
        buildNoteHandlers(calls),
    );

    const addStyle = items.find((item) => item.id === 'add-style');
    assert.ok(addStyle);
    assert.equal(items[0].id, 'add-style');
    assert.equal(addStyle.onSelect, undefined);
    assert.deepEqual(
        addStyle.submenu.map((item) => ({ id: item.id, label: item.label })),
        [
            { id: 'add-style-red', label: 'Red' },
            { id: 'add-style-markdown', label: 'Markdown' },
        ],
    );
    addStyle.submenu[0].onSelect();
    assert.deepEqual(calls, [['addStyle', 'note-123', '@red']]);

    const viewItems = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123' },
        buildNoteHandlers([]),
    );
    assert.equal(viewItems.some((item) => item.id === 'add-style'), false);
});

test('buildContextMenuItems places Remove Formatting directly beneath Add Style while editing', () => {
    const calls = [];
    const items = buildContextMenuItems(
        {
            kind: 'note',
            noteId: 'note-123',
            canAddStyle: true,
            canRemoveFormatting: true,
            styleOptions: [
                { id: 'red', label: 'Red', tag: '@red' },
            ],
        },
        buildNoteHandlers(calls),
    );

    assert.deepEqual(items.slice(0, 2).map((item) => item.id), [
        'add-style',
        'remove-formatting',
    ]);
    items[1].onSelect();
    assert.deepEqual(calls, [['removeFormatting', 'note-123']]);
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

test('buildContextMenuItems adds a top note action to non-editing note context', () => {
    const calls = [];
    const items = buildContextMenuItems(
        { kind: 'note', noteId: 'note-123', canAddNoteAtTop: true },
        buildNoteHandlers(calls),
    );

    const addNoteAtTop = items.find((item) => item.id === 'add-note-at-top');
    assert.ok(addNoteAtTop);
    assert.equal(addNoteAtTop.label, 'Add Note at Top');
    addNoteAtTop.onSelect();
    assert.deepEqual(calls, [['addNoteAtTop']]);
});

test('buildContextMenuItems returns view visibility toggles and export action', () => {
    const calls = [];
    const items = buildContextMenuItems(
        {
            kind: 'view',
            areTabsVisible: false,
            isCalendarVisible: true,
            areNoteTagsVisible: false,
            areNoteTimestampsVisible: true,
        },
        {
            onToggleTabs: (nextValue) => calls.push(['toggleTabs', nextValue]),
            onToggleCalendar: (nextValue) => calls.push(['toggleCalendar', nextValue]),
            onToggleNoteTags: (nextValue) => calls.push(['toggleNoteTags', nextValue]),
            onToggleNoteTimestamps: (nextValue) => calls.push(['toggleNoteTimestamps', nextValue]),
            onExportViewHtml: () => calls.push(['exportViewHtml']),
        },
    );

    assert.deepEqual(
        items.map((item) => ({ id: item.id, label: item.label, enabled: item.enabled })),
        [
            { id: 'toggle-tabs', label: 'Show Tabs', enabled: true },
            { id: 'toggle-calendar-view', label: 'Hide Calendar View', enabled: true },
            { id: 'toggle-note-tags', label: 'Show Tags in List', enabled: true },
            { id: 'toggle-note-timestamps', label: 'Hide Note Timestamps', enabled: true },
            { id: 'export-view-html', label: 'Export View as HTML', enabled: true },
        ],
    );

    for (const item of items) {
        item.onSelect();
    }
    assert.deepEqual(calls, [
        ['toggleTabs', true],
        ['toggleCalendar', false],
        ['toggleNoteTags', true],
        ['toggleNoteTimestamps', false],
        ['exportViewHtml'],
    ]);
});

test('view context menu persists the note timestamp visibility preference', async () => {
    const source = await readFile(CONTEXT_MENU_EVENTS_URL, 'utf8');
    const viewMenuStart = source.indexOf('function showViewContextMenu(event)');
    const viewMenuEnd = source.indexOf('function handleContextMenu(event)', viewMenuStart);

    assert.ok(viewMenuStart >= 0);
    assert.ok(viewMenuEnd > viewMenuStart);
    const viewMenuSource = source.slice(viewMenuStart, viewMenuEnd);
    assert.match(
        viewMenuSource,
        /areNoteTimestampsVisible: document\.body\.classList\.contains\('pref-show-note-timestamps'\)/,
    );
    assert.match(
        viewMenuSource,
        /onToggleNoteTimestamps:[\s\S]*CommandPalette\.applyPreference\('pref\.show_note_timestamps', nextValue\)/,
    );
});

test('buildContextMenuItems adds a top note action to non-editing blank view context', () => {
    const calls = [];
    const items = buildContextMenuItems(
        {
            kind: 'view',
            areTabsVisible: true,
            isCalendarVisible: true,
            areNoteTagsVisible: true,
            areNoteTimestampsVisible: true,
            canAddNoteAtTop: true,
        },
        {
            onAddNoteAtTop: () => calls.push(['addNoteAtTop']),
            onToggleTabs: () => {},
            onToggleCalendar: () => {},
            onToggleNoteTags: () => {},
            onToggleNoteTimestamps: () => {},
            onExportViewHtml: () => {},
        },
    );

    assert.equal(items[0].id, 'add-note-at-top');
    assert.equal(items[0].label, 'Add Note at Top');
    items[0].onSelect();
    assert.deepEqual(calls, [['addNoteAtTop']]);
});

test('buildContextMenuItems returns only link actions for link context', () => {
    const calls = [];
    const linkContext = { href: 'https://example.com/docs' };
    const items = buildContextMenuItems(
        { kind: 'link', linkContext },
        {
            onCopyLink: (context) => calls.push(['copyLink', context]),
            onOpenLinkInNewTab: (context) => calls.push(['openLink', context]),
        },
    );

    assert.deepEqual(
        items.map((item) => ({ id: item.id, label: item.label, enabled: item.enabled })),
        [
            { id: 'copy-link', label: 'Copy Link', enabled: true },
            { id: 'open-link-new-tab', label: 'Open Link in New Tab', enabled: true },
        ],
    );

    items[0].onSelect();
    items[1].onSelect();
    assert.deepEqual(calls, [
        ['copyLink', linkContext],
        ['openLink', linkContext],
    ]);
});

test('buildContextMenuItems includes source action for a link inside a reference', () => {
    const calls = [];
    const linkContext = { href: 'https://example.com/docs' };
    const items = buildContextMenuItems(
        {
            kind: 'link',
            linkContext,
            referenceNoteId: 'source-note-456',
        },
        {
            onOpenReferenceSource: (referenceNoteId) => calls.push(['source', referenceNoteId]),
            onCopyLink: (context) => calls.push(['copyLink', context]),
            onOpenLinkInNewTab: (context) => calls.push(['openLink', context]),
        },
    );

    assert.deepEqual(items.map((item) => item.id), [
        'open-reference-source',
        'copy-link',
        'open-link-new-tab',
    ]);
    assert.equal(items[1].separated, true);
    items[0].onSelect();
    assert.deepEqual(calls, [['source', 'source-note-456']]);
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
