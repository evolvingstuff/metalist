export const DEFAULT_SEARCH_SUGGESTION_WINDOWS_VALUE = '[1,7,30]';
export const MAX_SEARCH_SUGGESTION_WINDOW_DAYS = 365;
export const MAX_SEARCH_SUGGESTION_WINDOW_SLOTS = 20;

let currentWindowDays = Object.freeze([1, 7, 30]);

export function getSearchSuggestionWindowsValidationError(windowDays) {
    if (!Array.isArray(windowDays)) {
        return 'Search suggestion windows must be an array';
    }
    if (windowDays.length > MAX_SEARCH_SUGGESTION_WINDOW_SLOTS) {
        return `Search suggestion windows cannot contain more than ${MAX_SEARCH_SUGGESTION_WINDOW_SLOTS} slots`;
    }
    const seen = new Set();
    for (const dayCount of windowDays) {
        if (!Number.isInteger(dayCount)) {
            return 'Search suggestion windows must contain integers';
        }
        if (dayCount < 1 || dayCount > MAX_SEARCH_SUGGESTION_WINDOW_DAYS) {
            return `Search suggestion windows must be between 1 and ${MAX_SEARCH_SUGGESTION_WINDOW_DAYS} days`;
        }
        if (seen.has(dayCount)) {
            return 'Search suggestion windows cannot contain duplicates';
        }
        seen.add(dayCount);
    }
    return '';
}

export function validateSearchSuggestionWindows(windowDays) {
    const validationError = getSearchSuggestionWindowsValidationError(windowDays);
    if (validationError !== '') {
        throw new Error(validationError);
    }
    return windowDays.slice();
}

export function parseSearchSuggestionWindowsValue(value) {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error('Search suggestion windows preference must be a non-empty string');
    }
    const parsed = JSON.parse(value);
    return validateSearchSuggestionWindows(parsed);
}

export function serializeSearchSuggestionWindows(windowDays) {
    return JSON.stringify(validateSearchSuggestionWindows(windowDays));
}

export function setSearchSuggestionWindowsValue(value) {
    currentWindowDays = Object.freeze(parseSearchSuggestionWindowsValue(value));
}

export function getSearchSuggestionWindowDays() {
    return currentWindowDays.slice();
}
