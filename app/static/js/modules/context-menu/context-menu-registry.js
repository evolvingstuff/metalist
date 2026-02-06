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

    return [];
}
