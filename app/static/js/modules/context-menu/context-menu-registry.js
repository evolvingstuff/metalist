function buildTagContextItems(context, handlers) {
    if (!context || typeof context !== 'object') {
        throw new Error('buildTagContextItems requires context object');
    }
    if (!handlers || typeof handlers !== 'object') {
        throw new Error('buildTagContextItems requires handlers object');
    }

    const tag = context.tag;
    if (typeof tag !== 'string' || tag.trim() === '') {
        throw new Error('Tag context missing tag');
    }
    const onEditTagRelationships = handlers.onEditTagRelationships;
    if (typeof onEditTagRelationships !== 'function') {
        throw new Error('Tag context missing onEditTagRelationships handler');
    }

    return [
        {
            id: 'edit-tag-relationships',
            label: 'Edit Tag Relationships',
            icon: 'link',
            enabled: true,
            onSelect: () => onEditTagRelationships(tag),
        },
    ];
}

function buildNoteContextItems(context, handlers) {
    if (!context || typeof context !== 'object') {
        throw new Error('buildNoteContextItems requires context object');
    }
    if (!handlers || typeof handlers !== 'object') {
        throw new Error('buildNoteContextItems requires handlers object');
    }

    const noteId = context.noteId;
    if (typeof noteId !== 'string' || noteId.trim() === '') {
        throw new Error('Note context missing noteId');
    }

    const onAddSiblingNote = handlers.onAddSiblingNote;
    const onAddChildNote = handlers.onAddChildNote;
    const onDeleteNote = handlers.onDeleteNote;
    const onMoveNoteToTop = handlers.onMoveNoteToTop;
    const onCopySelection = handlers.onCopySelection;
    const onAddSelectionAsTag = handlers.onAddSelectionAsTag;
    const onCopyNote = handlers.onCopyNote;
    const onPasteNote = handlers.onPasteNote;
    const onPasteNoteChild = handlers.onPasteNoteChild;
    const onPasteReference = handlers.onPasteReference;
    const onPasteReferenceChild = handlers.onPasteReferenceChild;
    const onCopyImage = handlers.onCopyImage;
    const onSaveImage = handlers.onSaveImage;
    const onZoomImage = handlers.onZoomImage;
    const onOpenImageInNewTab = handlers.onOpenImageInNewTab;
    const onExportNoteHtml = handlers.onExportNoteHtml;
    const onExportViewHtml = handlers.onExportViewHtml;
    if (typeof onAddSiblingNote !== 'function') {
        throw new Error('Note context missing onAddSiblingNote handler');
    }
    if (typeof onAddChildNote !== 'function') {
        throw new Error('Note context missing onAddChildNote handler');
    }
    if (typeof onDeleteNote !== 'function') {
        throw new Error('Note context missing onDeleteNote handler');
    }
    if (typeof onMoveNoteToTop !== 'function') {
        throw new Error('Note context missing onMoveNoteToTop handler');
    }
    if (typeof onCopySelection !== 'function') {
        throw new Error('Note context missing onCopySelection handler');
    }
    if (typeof onAddSelectionAsTag !== 'function') {
        throw new Error('Note context missing onAddSelectionAsTag handler');
    }
    if (typeof onCopyNote !== 'function') {
        throw new Error('Note context missing onCopyNote handler');
    }
    if (typeof onPasteNote !== 'function') {
        throw new Error('Note context missing onPasteNote handler');
    }
    if (typeof onPasteNoteChild !== 'function') {
        throw new Error('Note context missing onPasteNoteChild handler');
    }
    if (typeof onPasteReference !== 'function') {
        throw new Error('Note context missing onPasteReference handler');
    }
    if (typeof onPasteReferenceChild !== 'function') {
        throw new Error('Note context missing onPasteReferenceChild handler');
    }
    if (typeof onExportNoteHtml !== 'function') {
        throw new Error('Note context missing onExportNoteHtml handler');
    }
    if (typeof onExportViewHtml !== 'function') {
        throw new Error('Note context missing onExportViewHtml handler');
    }

    const items = [];
    const imageContext = context.imageContext;
    if (imageContext !== null && typeof imageContext === 'object') {
        if (typeof onCopyImage !== 'function') {
            throw new Error('Image note context missing onCopyImage handler');
        }
        if (typeof onSaveImage !== 'function') {
            throw new Error('Image note context missing onSaveImage handler');
        }
        if (typeof onZoomImage !== 'function') {
            throw new Error('Image note context missing onZoomImage handler');
        }
        if (typeof onOpenImageInNewTab !== 'function') {
            throw new Error('Image note context missing onOpenImageInNewTab handler');
        }

        items.push(
            {
                id: 'copy-image',
                label: 'Copy Image',
                icon: 'image',
                enabled: true,
                onSelect: () => onCopyImage(imageContext),
            },
            {
                id: 'save-image',
                label: 'Save Image',
                icon: 'download',
                enabled: true,
                onSelect: () => onSaveImage(imageContext),
            },
            {
                id: 'zoom-image',
                label: 'Zoom Image',
                icon: 'zoom',
                enabled: true,
                onSelect: () => onZoomImage(imageContext),
            },
            {
                id: 'open-image-new-tab',
                label: 'Open Image in New Tab',
                icon: 'external',
                enabled: true,
                onSelect: () => onOpenImageInNewTab(imageContext),
            },
        );
    }

    const hasSelectedText = context.hasSelectedText === true;
    const hasNoteClipboard = context.hasNoteClipboard === true;
    const copyItem = {
        id: hasSelectedText ? 'copy-selection' : 'copy-note',
        label: hasSelectedText ? 'Copy' : 'Copy Note',
        icon: 'copy',
        enabled: true,
        onSelect: () => {
            if (hasSelectedText) {
                onCopySelection(noteId);
                return;
            }
            onCopyNote(noteId);
        },
    };
    if (items.length > 0) {
        copyItem.separated = true;
    }
    items.push(copyItem);

    const selectedTextForTag = context.selectedTextForTag;
    if (selectedTextForTag !== undefined) {
        if (typeof selectedTextForTag !== 'string' || selectedTextForTag.length === 0) {
            throw new Error('Note context selectedTextForTag must be a non-empty string when provided');
        }
        if (!hasSelectedText) {
            throw new Error('Note context cannot add selected text as tag without selected text');
        }
        items.push({
            id: 'add-selection-as-tag',
            label: 'Add as Tag',
            icon: 'tag',
            enabled: true,
            onSelect: () => onAddSelectionAsTag(noteId, selectedTextForTag),
        });
    }

    if (hasNoteClipboard) {
        items.push(
            {
                id: 'paste-note',
                label: 'Paste Sibling Note',
                icon: 'paste',
                enabled: true,
                onSelect: () => onPasteNote(noteId),
            },
            {
                id: 'paste-note-child',
                label: 'Paste Child Note',
                icon: 'paste_child',
                enabled: true,
                onSelect: () => onPasteNoteChild(noteId),
            },
            {
                id: 'paste-reference',
                label: 'Paste Sibling Reference',
                icon: 'link',
                enabled: true,
                onSelect: () => onPasteReference(noteId),
            },
            {
                id: 'paste-reference-child',
                label: 'Paste Child Reference',
                icon: 'link_child',
                enabled: true,
                onSelect: () => onPasteReferenceChild(noteId),
            },
        );
    }

    const addSiblingItem = {
        id: 'add-sibling-note',
        label: 'Add Sibling Note',
        icon: 'add_sibling',
        enabled: true,
        onSelect: () => onAddSiblingNote(noteId),
    };
    items.push(
        addSiblingItem,
        {
            id: 'add-child-note',
            label: 'Add Child Note',
            icon: 'add_child',
            enabled: true,
            onSelect: () => onAddChildNote(noteId),
        },
        {
            id: 'delete-note',
            label: 'Delete Note',
            icon: 'trash',
            enabled: true,
            onSelect: () => onDeleteNote(noteId),
        },
        {
            id: 'move-note-to-top',
            label: 'Move Note to Top',
            icon: 'arrow_top',
            enabled: true,
            onSelect: () => onMoveNoteToTop(noteId),
        },
    );
    items.push(
        {
            id: 'export-note-html',
            label: 'Export Note as HTML',
            icon: 'download',
            enabled: true,
            separated: true,
            onSelect: () => onExportNoteHtml(noteId),
        },
        {
            id: 'export-view-html',
            label: 'Export View as HTML',
            icon: 'download',
            enabled: true,
            onSelect: () => onExportViewHtml(),
        },
    );
    return items;
}

function buildLinkContextItems(context, handlers) {
    if (!context || typeof context !== 'object') {
        throw new Error('buildLinkContextItems requires context object');
    }
    if (!handlers || typeof handlers !== 'object') {
        throw new Error('buildLinkContextItems requires handlers object');
    }

    const linkContext = context.linkContext;
    if (linkContext === null || typeof linkContext !== 'object') {
        throw new Error('Link context missing linkContext');
    }
    const href = linkContext.href;
    if (typeof href !== 'string' || href.trim() === '') {
        throw new Error('Link context missing href');
    }

    const onCopyLink = handlers.onCopyLink;
    const onOpenLinkInNewTab = handlers.onOpenLinkInNewTab;
    if (typeof onCopyLink !== 'function') {
        throw new Error('Link context missing onCopyLink handler');
    }
    if (typeof onOpenLinkInNewTab !== 'function') {
        throw new Error('Link context missing onOpenLinkInNewTab handler');
    }

    return [
        {
            id: 'copy-link',
            label: 'Copy Link',
            icon: 'copy',
            enabled: true,
            onSelect: () => onCopyLink(linkContext),
        },
        {
            id: 'open-link-new-tab',
            label: 'Open Link in New Tab',
            icon: 'external',
            enabled: true,
            onSelect: () => onOpenLinkInNewTab(linkContext),
        },
    ];
}

function buildViewContextItems(context, handlers) {
    if (!context || typeof context !== 'object') {
        throw new Error('buildViewContextItems requires context object');
    }
    if (!handlers || typeof handlers !== 'object') {
        throw new Error('buildViewContextItems requires handlers object');
    }

    const onExportViewHtml = handlers.onExportViewHtml;
    if (typeof onExportViewHtml !== 'function') {
        throw new Error('View context missing onExportViewHtml handler');
    }

    return [
        {
            id: 'export-view-html',
            label: 'Export View as HTML',
            icon: 'download',
            enabled: true,
            onSelect: () => onExportViewHtml(),
        },
    ];
}

export function buildContextMenuItems(context, handlers) {
    if (!context || typeof context !== 'object') {
        throw new Error('buildContextMenuItems requires context object');
    }
    const kind = context.kind;
    if (typeof kind !== 'string' || kind.trim() === '') {
        throw new Error('buildContextMenuItems requires context.kind string');
    }

    if (kind === 'tag') {
        return buildTagContextItems(context, handlers);
    }
    if (kind === 'note') {
        return buildNoteContextItems(context, handlers);
    }
    if (kind === 'link') {
        return buildLinkContextItems(context, handlers);
    }
    if (kind === 'view') {
        return buildViewContextItems(context, handlers);
    }

    return [];
}
