import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveVerticalSiblingDropDestination } from '../../app/static/js/modules/mode-manager/services/note-drag-service.js';

test('resolveVerticalSiblingDropDestination moves to the top slot when dropped above the first sibling midpoint', () => {
    const destination = resolveVerticalSiblingDropDestination({
        siblingPlacements: [
            { id: 'A', midY: 100 },
            { id: 'B', midY: 200 },
            { id: 'C', midY: 300 },
            { id: 'D', midY: 400 },
        ],
        dropY: 40,
        currentPrevId: 'D',
        currentNextId: null,
    });

    assert.deepEqual(destination, {
        siblingId: 'A',
        position: 'BEFORE',
        newParentId: null,
    });
});

test('resolveVerticalSiblingDropDestination moves to the bottom slot when dropped below the last sibling midpoint', () => {
    const destination = resolveVerticalSiblingDropDestination({
        siblingPlacements: [
            { id: 'B', midY: 200 },
            { id: 'C', midY: 300 },
            { id: 'D', midY: 400 },
            { id: 'E', midY: 500 },
        ],
        dropY: 800,
        currentPrevId: null,
        currentNextId: 'B',
        parentId: 'parent-1',
    });

    assert.deepEqual(destination, {
        siblingId: 'E',
        position: 'AFTER',
        newParentId: 'parent-1',
    });
});

test('resolveVerticalSiblingDropDestination returns null for a no-op drop between the current neighbors', () => {
    const destination = resolveVerticalSiblingDropDestination({
        siblingPlacements: [
            { id: 'A', midY: 100 },
            { id: 'C', midY: 300 },
            { id: 'D', midY: 400 },
        ],
        dropY: 250,
        currentPrevId: 'A',
        currentNextId: 'C',
    });

    assert.equal(destination, null);
});
