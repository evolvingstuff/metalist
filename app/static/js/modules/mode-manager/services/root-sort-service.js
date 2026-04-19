export const ROOT_SORT_MODES = Object.freeze({
    NORMAL: 'normal',
    CREATED: 'created',
    UPDATED: 'updated',
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
    ) {
        throw new Error(`Unsupported root sort mode: ${sortMode}`);
    }
    return normalized;
}

export function isRootReorderLocked(sortMode) {
    return normalizeRootSortMode(sortMode) !== ROOT_SORT_MODES.NORMAL;
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
    throw new Error(`Unsupported root sort mode: ${sortMode}`);
}

export function buildRootDateSeparatorPlan(rootIds, rootSortBuckets) {
    if (!Array.isArray(rootIds)) {
        throw new Error('rootIds must be an array');
    }
    if (!rootSortBuckets || typeof rootSortBuckets !== 'object') {
        throw new Error('rootSortBuckets must be an object');
    }

    const plan = [];
    let previousKey = null;
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
