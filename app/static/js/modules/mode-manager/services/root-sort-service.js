export const ROOT_SORT_MODES = Object.freeze({
    NORMAL: 'normal',
    CREATED: 'created',
    UPDATED: 'updated',
    ALPHABETICAL: 'alphabetical',
    CONTENT_VOLUME: 'content-volume',
});

export function normalizeRootSortMode(sortMode) {
    if (typeof sortMode !== 'string') {
        throw new Error('sortMode must be a string');
    }
    const normalized = sortMode.trim().toLowerCase();
    if (
        normalized !== ROOT_SORT_MODES.NORMAL
        && normalized !== ROOT_SORT_MODES.CREATED
        && normalized !== ROOT_SORT_MODES.UPDATED
        && normalized !== ROOT_SORT_MODES.ALPHABETICAL
        && normalized !== ROOT_SORT_MODES.CONTENT_VOLUME
    ) {
        throw new Error(`Unsupported root sort mode: ${sortMode}`);
    }
    return normalized;
}

export function isRootReorderLocked(sortMode) {
    return normalizeRootSortMode(sortMode) !== ROOT_SORT_MODES.NORMAL;
}

// Where a new root note may be added in a sorted tab (docs/ui/controls.md,
// "Sorted tabs"). `placement` is 'top' (the top of the list) or 'below' (right
// after a root note: Cmd+Enter, split, paste as sibling). Returns the banner
// explaining a block, or null when allowed. Child notes are never blocked: the
// root sort does not order them.
export function rootNoteCreationBlockMessage(sortMode, placement) {
    if (placement !== 'top' && placement !== 'below') {
        throw new Error(`Unknown root note placement: ${placement}`);
    }
    const normalized = normalizeRootSortMode(sortMode);
    if (normalized === ROOT_SORT_MODES.NORMAL) {
        return null;
    }
    if (isRootDateBucketSortMode(normalized)) {
        if (placement === 'top') {
            return null;
        }
        return 'In this sort order new root notes can only be added at the top (press Enter outside edit mode). '
            + 'Switch to Normal order to add one here; child notes can still be added.';
    }
    return 'New root notes cannot be added while this sort order is active, because they would land far from here. '
        + 'Switch to Normal order, or add a child note.';
}

export function getRootSortModeIndicatorLabel(sortMode) {
    const normalized = normalizeRootSortMode(sortMode);
    if (normalized === ROOT_SORT_MODES.NORMAL) {
        return '';
    }
    if (normalized === ROOT_SORT_MODES.CREATED) {
        return 'Sorted by datetime created';
    }
    if (normalized === ROOT_SORT_MODES.UPDATED) {
        return 'Sorted by datetime last updated';
    }
    if (normalized === ROOT_SORT_MODES.ALPHABETICAL) {
        return 'Sorted alphabetically';
    }
    if (normalized === ROOT_SORT_MODES.CONTENT_VOLUME) {
        return 'Sorted by content volume';
    }
    throw new Error(`Unsupported root sort mode: ${sortMode}`);
}

export function isRootDateBucketSortMode(sortMode) {
    const normalized = normalizeRootSortMode(sortMode);
    if (normalized === ROOT_SORT_MODES.CREATED) {
        return true;
    }
    if (normalized === ROOT_SORT_MODES.UPDATED) {
        return true;
    }
    return false;
}

// sortKeyBeforeWindow: the date bucket of the root just above the loaded band
// ('' at the first root), so a band that starts mid-day shows no header.
export function buildRootDateSeparatorPlan(rootIds, rootSortBuckets, sortKeyBeforeWindow) {
    if (!Array.isArray(rootIds)) {
        throw new Error('rootIds must be an array');
    }
    if (!rootSortBuckets || typeof rootSortBuckets !== 'object') {
        throw new Error('rootSortBuckets must be an object');
    }

    if (typeof sortKeyBeforeWindow !== 'string') {
        throw new Error('sortKeyBeforeWindow must be a string');
    }
    const plan = [];
    let previousKey = sortKeyBeforeWindow === '' ? null : sortKeyBeforeWindow;
    for (const rootId of rootIds) {
        if (typeof rootId !== 'string' || rootId.length === 0) {
            throw new Error('rootIds entries must be non-empty strings');
        }
        const bucket = rootSortBuckets[rootId];
        if (!bucket || typeof bucket !== 'object') {
            throw new Error(`Missing root sort bucket for ${rootId}`);
        }
        if (typeof bucket.key !== 'string' || bucket.key.length === 0) {
            throw new Error(`root sort bucket key missing for ${rootId}`);
        }
        if (typeof bucket.label !== 'string' || bucket.label.length === 0) {
            throw new Error(`root sort bucket label missing for ${rootId}`);
        }
        if (bucket.key !== previousKey) {
            plan.push({
                rootId,
                bucketKey: bucket.key,
                label: bucket.label,
            });
            previousKey = bucket.key;
        }
    }
    return plan;
}
