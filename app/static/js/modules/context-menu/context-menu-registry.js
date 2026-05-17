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
    const onCopyImage = handlers.onCopyImage;
    const onSaveImage = handlers.onSaveImage;
    const onZoomImage = handlers.onZoomImage;
    const onOpenImageInNewTab = handlers.onOpenImageInNewTab;
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
                enabled: true,
                onSelect: () => onCopyImage(imageContext),
            },
            {
                id: 'save-image',
                label: 'Save Image',
                enabled: true,
                onSelect: () => onSaveImage(imageContext),
            },
            {
                id: 'zoom-image',
                label: 'Zoom Image',
                enabled: true,
                onSelect: () => onZoomImage(imageContext),
            },
            {
                id: 'open-image-new-tab',
                label: 'Open Image in New Tab',
                enabled: true,
                onSelect: () => onOpenImageInNewTab(imageContext),
            },
        );
    }

    const addSiblingItem = {
        id: 'add-sibling-note',
        label: 'Add Sibling Note',
        enabled: true,
        onSelect: () => onAddSiblingNote(noteId),
    };
    if (items.length > 0) {
        addSiblingItem.separated = true;
    }

    items.push(
        addSiblingItem,
        {
            id: 'add-child-note',
            label: 'Add Child Note',
            enabled: true,
            onSelect: () => onAddChildNote(noteId),
        },
        {
            id: 'delete-note',
            label: 'Delete Note',
            enabled: true,
            onSelect: () => onDeleteNote(noteId),
        },
        {
            id: 'move-note-to-top',
            label: 'Move Note to Top',
            enabled: true,
            onSelect: () => onMoveNoteToTop(noteId),
        },
    );
    return items;
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

    return [];
}
