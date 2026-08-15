import { analyzeSearchQueryInput, enforceSearchQueryInputForEditing } from './search-syntax-service.js';

const SEARCH_INVALID_CLASS = 'search-invalid';

export function resolveSearchInputDisplayQuery(searchQuery, isUntaggedView) {
    if (typeof searchQuery !== 'string') {
        throw new Error('resolveSearchInputDisplayQuery requires searchQuery string');
    }
    if (typeof isUntaggedView !== 'boolean') {
        throw new Error('resolveSearchInputDisplayQuery requires isUntaggedView boolean');
    }
    return isUntaggedView ? '' : searchQuery;
}

function ensureSearchValidationMessageElement() {
    const message = document.getElementById('search-validation-message');
    if (!message) {
        throw new Error('search-validation-message element missing from DOM');
    }
    return message;
}

export function setSearchValidationState(searchInput, analysis) {
    if (!searchInput) {
        throw new Error('setSearchValidationState requires search input element');
    }
    if (!analysis || typeof analysis.isComplete !== 'boolean') {
        throw new Error('setSearchValidationState requires analysis result');
    }

    const message = ensureSearchValidationMessageElement();

    const shouldWarn = typeof analysis.warningMessage === 'string' && analysis.warningMessage.length > 0;
    searchInput.classList.toggle(SEARCH_INVALID_CLASS, shouldWarn);

    if (shouldWarn) {
        message.textContent = analysis.warningMessage;
        message.hidden = false;
        return;
    }

    message.textContent = '';
    message.hidden = true;
}

export function enforceSearchInputElement(searchInput) {
    if (!searchInput || typeof searchInput.value !== 'string') {
        throw new Error('enforceSearchInputElement requires a search input element');
    }

    const rawValue = searchInput.value;
    const enforcedValue = enforceSearchQueryInputForEditing(rawValue);
    if (enforcedValue === rawValue) {
        return rawValue;
    }

    const selectionStart = Number.isInteger(searchInput.selectionStart) ? searchInput.selectionStart : rawValue.length;
    const selectionEnd = Number.isInteger(searchInput.selectionEnd) ? searchInput.selectionEnd : selectionStart;

    const nextSelectionStart = enforceSearchQueryInputForEditing(rawValue.slice(0, selectionStart)).length;
    const nextSelectionEnd = enforceSearchQueryInputForEditing(rawValue.slice(0, selectionEnd)).length;

    searchInput.value = enforcedValue;
    if (typeof searchInput.setSelectionRange === 'function') {
        searchInput.setSelectionRange(nextSelectionStart, nextSelectionEnd);
    }

    return enforcedValue;
}

export function syncSearchInputValue(searchInput, rawSearchQuery) {
    if (!searchInput || typeof searchInput.value !== 'string') {
        throw new Error('syncSearchInputValue requires a search input element');
    }
    if (typeof rawSearchQuery !== 'string') {
        throw new Error('syncSearchInputValue requires rawSearchQuery string');
    }

    const enforcedValue = enforceSearchQueryInputForEditing(rawSearchQuery);
    searchInput.value = enforcedValue;

    const analysis = analyzeSearchQueryInput(enforcedValue);
    setSearchValidationState(searchInput, analysis);
    return analysis;
}

export function blurFocusedSearchInput() {
    const searchInput = document.getElementById('search-input');
    if (!searchInput) {
        return false;
    }
    if (document.activeElement !== searchInput) {
        return false;
    }
    if (typeof searchInput.blur !== 'function') {
        throw new Error('search-input must support blur()');
    }
    searchInput.blur();
    return true;
}

export function focusSearchInputAndSelectAllText() {
    const searchInput = document.getElementById('search-input');
    if (!searchInput) {
        return false;
    }
    if (typeof searchInput.value !== 'string') {
        throw new Error('search-input must expose string value');
    }
    if (typeof searchInput.focus !== 'function') {
        throw new Error('search-input must support focus()');
    }
    if (typeof searchInput.setSelectionRange !== 'function') {
        throw new Error('search-input must support setSelectionRange()');
    }

    searchInput.focus({ preventScroll: true });
    searchInput.setSelectionRange(0, searchInput.value.length);
    return true;
}
