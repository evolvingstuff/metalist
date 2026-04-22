const BOTTOM_LEFT_CLASS = 'search-contexts-list--bottom-left';
const SEARCH_CONTEXTS_SELECTOR = '#search-contexts-list';
const SEARCH_INPUT_ROW_SELECTOR = '.controls .search-input-row';
const OVERLAP_MARGIN_PX = 8;

function getSearchContextsListElement() {
    const element = document.querySelector(SEARCH_CONTEXTS_SELECTOR);
    if (!element) {
        return null;
    }
    if (!(element instanceof HTMLElement)) {
        throw new Error('search-contexts-list must be an HTMLElement');
    }
    return element;
}

function getSearchInputRowElement() {
    const element = document.querySelector(SEARCH_INPUT_ROW_SELECTOR);
    if (!element) {
        throw new Error('search-input-row element missing from DOM');
    }
    if (!(element instanceof HTMLElement)) {
        throw new Error('search-input-row must be an HTMLElement');
    }
    return element;
}

function rectsOverlap(rectA, rectB, marginPx) {
    const hasRectShape = rect => rect
        && typeof rect === 'object'
        && ['top', 'right', 'bottom', 'left'].every(key => typeof rect[key] === 'number' && !Number.isNaN(rect[key]));
    if (!hasRectShape(rectA) || !hasRectShape(rectB)) {
        throw new Error('rectsOverlap requires rect-like objects with numeric top/right/bottom/left');
    }
    if (typeof marginPx !== 'number' || Number.isNaN(marginPx) || marginPx < 0) {
        throw new Error('rectsOverlap requires non-negative numeric marginPx');
    }

    return !(
        rectA.right <= rectB.left - marginPx
        || rectA.left >= rectB.right + marginPx
        || rectA.bottom <= rectB.top - marginPx
        || rectA.top >= rectB.bottom + marginPx
    );
}

export function isSearchContextsOverlayBottomLeft() {
    const element = getSearchContextsListElement();
    if (!element) {
        return false;
    }
    return element.classList.contains(BOTTOM_LEFT_CLASS);
}

export function updateSearchContextsOverlayPlacement() {
    const searchContextsList = getSearchContextsListElement();
    if (!searchContextsList) {
        return false;
    }

    searchContextsList.classList.remove(BOTTOM_LEFT_CLASS);

    const isVisible = window.getComputedStyle(searchContextsList).display !== 'none';
    if (!isVisible) {
        return false;
    }

    const searchInputRow = getSearchInputRowElement();
    const shouldMoveBottomLeft = rectsOverlap(
        searchContextsList.getBoundingClientRect(),
        searchInputRow.getBoundingClientRect(),
        OVERLAP_MARGIN_PX,
    );

    if (shouldMoveBottomLeft) {
        searchContextsList.classList.add(BOTTOM_LEFT_CLASS);
    }

    return shouldMoveBottomLeft;
}
