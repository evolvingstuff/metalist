import {
    ROOT_SORT_MODES,
    getRootSortModeIndicatorLabel,
    normalizeRootSortMode,
} from './root-sort-service.js';

export function updateRootSortIndicator(snapshot) {
    if (!snapshot || typeof snapshot !== 'object') {
        throw new Error('updateRootSortIndicator requires snapshot object');
    }

    const indicator = document.getElementById('root-sort-indicator');
    if (!(indicator instanceof HTMLElement)) {
        throw new Error('root-sort-indicator element missing');
    }
    const label = document.getElementById('root-sort-indicator-label');
    if (!(label instanceof HTMLElement)) {
        throw new Error('root-sort-indicator-label element missing');
    }

    const sortMode = normalizeRootSortMode(snapshot.sortMode);
    indicator.dataset.sortMode = sortMode;
    if (sortMode === ROOT_SORT_MODES.NORMAL) {
        label.textContent = '';
        indicator.hidden = true;
        return;
    }

    label.textContent = getRootSortModeIndicatorLabel(sortMode);
    indicator.hidden = false;
}
