function requireNonNegativeInteger(name, value) {
    if (!Number.isInteger(value) || value < 0) {
        throw new Error(`${name} must be a non-negative integer`);
    }
}

function requireTabId(name, value) {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`${name} must be a non-empty string`);
    }
}

function requireCloneResult(cloneResult) {
    if (!cloneResult || typeof cloneResult !== 'object') {
        throw new Error('cloneResult must be an object');
    }
    if (typeof cloneResult.cloned !== 'boolean') {
        throw new Error('cloneResult.cloned must be a boolean');
    }
    if (!Number.isInteger(cloneResult.nodeCount) || cloneResult.nodeCount < 0) {
        throw new Error('cloneResult.nodeCount must be a non-negative integer');
    }
}

export function getDuplicateTabCloneOptions(sourceHashCount) {
    requireNonNegativeInteger('sourceHashCount', sourceHashCount);
    return {
        collectNoteHashes: sourceHashCount === 0,
    };
}

export function seedDuplicatedTabNoteHashes(options) {
    if (options === null || typeof options !== 'object') {
        throw new Error('seedDuplicatedTabNoteHashes requires options object');
    }

    const {
        sourceHashCount,
        sourceTabId,
        newTabId,
        cloneResult,
        cloneTabNoteHashes,
        seedTabNoteHashes,
    } = options;

    requireNonNegativeInteger('sourceHashCount', sourceHashCount);
    requireTabId('sourceTabId', sourceTabId);
    requireTabId('newTabId', newTabId);
    requireCloneResult(cloneResult);

    if (!cloneResult.cloned) {
        throw new Error('Cannot duplicate tab: source tab DOM is not cached');
    }

    if (cloneResult.nodeCount === 0) {
        return { seeded: false, strategy: 'empty-dom' };
    }

    if (sourceHashCount > 0) {
        if (typeof cloneTabNoteHashes !== 'function') {
            throw new Error('cloneTabNoteHashes must be a function');
        }
        const hashCloneResult = cloneTabNoteHashes(sourceTabId, newTabId);
        if (!hashCloneResult || typeof hashCloneResult !== 'object') {
            throw new Error('cloneTabNoteHashes must return an object');
        }
        if (hashCloneResult.cloned !== true) {
            throw new Error('Cannot duplicate tab: failed to seed diff cache for new tab');
        }
        return {
            seeded: true,
            strategy: 'clone-existing-cache',
        };
    }

    if (!(cloneResult.noteHashes instanceof Map)) {
        throw new Error('Cannot duplicate tab: failed to seed diff cache for new tab');
    }
    if (typeof seedTabNoteHashes !== 'function') {
        throw new Error('seedTabNoteHashes must be a function');
    }

    seedTabNoteHashes(newTabId, cloneResult.noteHashes);
    return {
        seeded: true,
        strategy: 'seed-from-cloned-dom',
    };
}
