const BOTTOM_LEFT_CLASS = 'search-contexts-list--bottom-left';
const SEARCH_CONTEXTS_SELECTOR = '#search-contexts-list';

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

    searchContextsList.classList.add(BOTTOM_LEFT_CLASS);
    return true;
}
