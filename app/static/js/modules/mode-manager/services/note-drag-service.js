function normalizeNullableNoteId(noteId, fieldName) {
    if (noteId === null) {
        return null;
    }
    if (typeof noteId !== 'string') {
        throw new Error(`${fieldName} must be a string or null`);
    }
    if (noteId.length === 0) {
        return null;
    }
    return noteId;
}

export function resolveVerticalSiblingDropDestination({
    siblingPlacements,
    dropY,
    currentPrevId = null,
    currentNextId = null,
    parentId = null,
}) {
    if (!Array.isArray(siblingPlacements)) {
        throw new Error('resolveVerticalSiblingDropDestination requires siblingPlacements array');
    }
    if (typeof dropY !== 'number' || Number.isNaN(dropY)) {
        throw new Error('resolveVerticalSiblingDropDestination requires numeric dropY');
    }

    const normalizedCurrentPrevId = normalizeNullableNoteId(currentPrevId, 'currentPrevId');
    const normalizedCurrentNextId = normalizeNullableNoteId(currentNextId, 'currentNextId');
    const normalizedParentId = normalizeNullableNoteId(parentId, 'parentId');

    if (siblingPlacements.length === 0) {
        return null;
    }

    const normalizedPlacements = siblingPlacements.map((placement, index) => {
        if (!placement || typeof placement !== 'object') {
            throw new Error(`siblingPlacements[${index}] must be an object`);
        }
        if (typeof placement.id !== 'string' || placement.id.length === 0) {
            throw new Error(`siblingPlacements[${index}].id must be a non-empty string`);
        }
        if (typeof placement.midY !== 'number' || Number.isNaN(placement.midY)) {
            throw new Error(`siblingPlacements[${index}].midY must be numeric`);
        }
        return placement;
    });

    let insertionIndex = 0;
    while (
        insertionIndex < normalizedPlacements.length
        && dropY >= normalizedPlacements[insertionIndex].midY
    ) {
        insertionIndex += 1;
    }

    const destinationPrevId = insertionIndex === 0 ? null : normalizedPlacements[insertionIndex - 1].id;
    const destinationNextId = insertionIndex === normalizedPlacements.length
        ? null
        : normalizedPlacements[insertionIndex].id;

    if (
        destinationPrevId === normalizedCurrentPrevId
        && destinationNextId === normalizedCurrentNextId
    ) {
        return null;
    }

    if (destinationNextId !== null) {
        return {
            siblingId: destinationNextId,
            position: 'BEFORE',
            newParentId: normalizedParentId,
        };
    }

    if (destinationPrevId !== null) {
        return {
            siblingId: destinationPrevId,
            position: 'AFTER',
            newParentId: normalizedParentId,
        };
    }

    return null;
}
