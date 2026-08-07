import assert from 'node:assert/strict';
import test from 'node:test';

import {
    ROOT_SORT_MODES,
    buildRootDateSeparatorPlan,
    getRootSortModeIndicatorLabel,
    isRootReorderLocked,
} from '../../app/static/js/modules/mode-manager/services/root-sort-service.js';

test('isRootReorderLocked locks every non-normal sort mode', () => {
    assert.equal(isRootReorderLocked(ROOT_SORT_MODES.NORMAL), false);
    assert.equal(isRootReorderLocked(ROOT_SORT_MODES.CREATED), true);
    assert.equal(isRootReorderLocked(ROOT_SORT_MODES.UPDATED), true);
    assert.equal(isRootReorderLocked(ROOT_SORT_MODES.ALPHABETICAL), true);
    assert.equal(isRootReorderLocked(ROOT_SORT_MODES.CONTENT_VOLUME), true);
});

test('buildRootDateSeparatorPlan emits one separator per day bucket transition', () => {
    const plan = buildRootDateSeparatorPlan(
        ['root-a', 'root-b', 'root-c', 'root-d'],
        {
            'root-a': { key: '2026-04-19', label: '2026/04/19 - Sunday' },
            'root-b': { key: '2026-04-19', label: '2026/04/19 - Sunday' },
            'root-c': { key: '2026-04-18', label: '2026/04/18 - Saturday' },
            'root-d': { key: '2026-04-17', label: '2026/04/17 - Friday' },
        },
    );

    assert.deepEqual(plan, [
        { rootId: 'root-a', bucketKey: '2026-04-19', label: '2026/04/19 - Sunday' },
        { rootId: 'root-c', bucketKey: '2026-04-18', label: '2026/04/18 - Saturday' },
        { rootId: 'root-d', bucketKey: '2026-04-17', label: '2026/04/17 - Friday' },
    ]);
});

test('getRootSortModeIndicatorLabel returns dismissible pill text for sorted modes', () => {
    assert.equal(getRootSortModeIndicatorLabel(ROOT_SORT_MODES.NORMAL), '');
    assert.equal(getRootSortModeIndicatorLabel(ROOT_SORT_MODES.CREATED), 'Sorted by datetime created');
    assert.equal(getRootSortModeIndicatorLabel(ROOT_SORT_MODES.UPDATED), 'Sorted by datetime last updated');
    assert.equal(getRootSortModeIndicatorLabel(ROOT_SORT_MODES.ALPHABETICAL), 'Sorted alphabetically');
    assert.equal(getRootSortModeIndicatorLabel(ROOT_SORT_MODES.CONTENT_VOLUME), 'Sorted by content volume');
});
