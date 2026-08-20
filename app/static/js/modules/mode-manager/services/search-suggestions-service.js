import { NotesAPI } from '../../api-client.js';
import { analyzeSearchQueryInput } from './search-syntax-service.js';
import { syncSearchInputValue } from './search-input-service.js';
import { getSearchSuggestionWindowDays } from './search-suggestion-windows-service.js';

const SUGGESTION_DEBOUNCE_MS = 50;
const HOVER_DISMISS_BOTTOM_BUFFER_PX = 25;
let pendingTimer = null;
let requestSerial = 0;
let selectedIndex = -1;
let suppressSuggestionsUntilInputInteraction = false;

function getSearchSuggestionsContainer() {
    const container = document.getElementById('search-suggestions');
    if (!container) {
        throw new Error('search-suggestions element missing from DOM');
    }
    return container;
}

function escapeHtml(value) {
    if (typeof value !== 'string') {
        throw new Error('escapeHtml requires a string');
    }
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function parseSuggestionContext(rawValue, cursorIndex) {
    if (typeof rawValue !== 'string') {
        throw new Error('parseSuggestionContext requires rawValue string');
    }
    if (!Number.isInteger(cursorIndex)) {
        throw new Error('parseSuggestionContext requires cursorIndex integer');
    }
    if (cursorIndex < 0 || cursorIndex > rawValue.length) {
        throw new Error('parseSuggestionContext cursorIndex out of bounds');
    }

    let quoteChar = null;
    let index = 0;
    while (index < cursorIndex) {
        const char = rawValue[index];
        if (char === '\\' && index + 1 < cursorIndex) {
            const nextChar = rawValue[index + 1];
            if (quoteChar && (nextChar === quoteChar || nextChar === '\\')) {
                index += 2;
                continue;
            }
        }
        if (quoteChar) {
            if (char === quoteChar) {
                quoteChar = null;
            }
            index += 1;
            continue;
        }
        if (char === '"' || char === "'") {
            quoteChar = char;
            index += 1;
            continue;
        }
        index += 1;
    }

    if (quoteChar) {
        return null;
    }

    let start = cursorIndex;
    while (start > 0 && !/\s/.test(rawValue[start - 1])) {
        start -= 1;
    }

    const token = rawValue.slice(start, cursorIndex);
    if (!token) {
        return {
            partialPrefix: '',
            prefixModifier: null,
            replaceStart: cursorIndex,
            replaceEnd: cursorIndex,
        };
    }

    let prefixModifier = null;
    let prefixValue = token;
    if (prefixValue[0] === '+' || prefixValue[0] === '-') {
        prefixModifier = prefixValue[0];
        prefixValue = prefixValue.slice(1);
    }

    if (!prefixValue) {
        return null;
    }

    return {
        partialPrefix: prefixValue,
        prefixModifier,
        replaceStart: start,
        replaceEnd: cursorIndex,
    };
}

function clearPendingSuggestionRequest() {
    if (pendingTimer) {
        clearTimeout(pendingTimer);
        pendingTimer = null;
    }
    requestSerial += 1;
}

function hideSuggestions(options) {
    let normalizedOptions = options;
    if (normalizedOptions === undefined) {
        normalizedOptions = {};
    }
    if (normalizedOptions === null || typeof normalizedOptions !== 'object') {
        throw new Error('hideSuggestions options must be an object');
    }
    if (normalizedOptions.suppressUntilInputInteraction === true) {
        suppressSuggestionsUntilInputInteraction = true;
    }
    if (normalizedOptions.invalidateRequests === true) {
        clearPendingSuggestionRequest();
    }

    const container = getSearchSuggestionsContainer();
    container.hidden = true;
    container.style.display = 'none';
    container.innerHTML = '';
    selectedIndex = -1;
}

function shouldHideForVerticalPointerPosition(container, pointerClientY) {
    if (!Number.isFinite(pointerClientY)) {
        throw new Error('pointerClientY must be finite');
    }
    if (typeof container.getBoundingClientRect !== 'function') {
        throw new Error('search-suggestions must support getBoundingClientRect()');
    }

    const suggestionsRect = container.getBoundingClientRect();
    if (!suggestionsRect || typeof suggestionsRect.bottom !== 'number') {
        throw new Error('search-suggestions rect missing bottom');
    }
    return pointerClientY > suggestionsRect.bottom + HOVER_DISMISS_BOTTOM_BUFFER_PX;
}

function shouldHideForHorizontalPointerPosition(pointerClientX) {
    if (!Number.isFinite(pointerClientX)) {
        throw new Error('pointerClientX must be finite');
    }

    const notesContainer = document.getElementById('notes-container');
    if (!notesContainer) {
        throw new Error('notes-container element missing from DOM');
    }
    if (typeof notesContainer.getBoundingClientRect !== 'function') {
        throw new Error('notes-container must support getBoundingClientRect()');
    }

    const notesRect = notesContainer.getBoundingClientRect();
    if (!notesRect || typeof notesRect.left !== 'number' || typeof notesRect.right !== 'number') {
        throw new Error('notes-container rect missing horizontal bounds');
    }
    if (pointerClientX < notesRect.left) {
        return true;
    }
    if (pointerClientX > notesRect.right) {
        return true;
    }
    return false;
}

export function hideSearchSuggestionsForSearchContextHover(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('hideSearchSuggestionsForSearchContextHover requires options');
    }
    const { isSearching, noteId, pointerClientY } = options;
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('hideSearchSuggestionsForSearchContextHover requires noteId');
    }
    if (!Number.isFinite(pointerClientY)) {
        throw new Error('hideSearchSuggestionsForSearchContextHover requires pointerClientY');
    }
    if (!isSearching) {
        return false;
    }

    const container = getSearchSuggestionsContainer();
    if (container.hidden) {
        return false;
    }
    if (!shouldHideForVerticalPointerPosition(container, pointerClientY)) {
        return false;
    }

    hideSuggestions({
        invalidateRequests: true,
        suppressUntilInputInteraction: true,
    });
    return true;
}

export function hideSearchSuggestionsForSearchContextPointerMove(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('hideSearchSuggestionsForSearchContextPointerMove requires options');
    }
    const { isSearching, pointerClientX, pointerClientY } = options;
    if (!Number.isFinite(pointerClientX)) {
        throw new Error('hideSearchSuggestionsForSearchContextPointerMove requires pointerClientX');
    }
    if (!Number.isFinite(pointerClientY)) {
        throw new Error('hideSearchSuggestionsForSearchContextPointerMove requires pointerClientY');
    }
    if (!isSearching) {
        return false;
    }

    const container = getSearchSuggestionsContainer();
    if (container.hidden) {
        return false;
    }

    let shouldHide = shouldHideForVerticalPointerPosition(container, pointerClientY);
    if (!shouldHide) {
        shouldHide = shouldHideForHorizontalPointerPosition(pointerClientX);
    }
    if (!shouldHide) {
        return false;
    }

    hideSuggestions({
        invalidateRequests: true,
        suppressUntilInputInteraction: true,
    });
    return true;
}

function applySuggestion(searchInput, suggestion) {
    if (!searchInput || typeof searchInput.value !== 'string') {
        throw new Error('applySuggestion requires searchInput element');
    }
    if (typeof suggestion !== 'string' || suggestion.length === 0) {
        throw new Error('applySuggestion requires suggestion string');
    }

    const rawValue = searchInput.value;
    if (!Number.isInteger(searchInput.selectionStart)) {
        throw new Error('searchInput.selectionStart missing');
    }
    const cursorIndex = searchInput.selectionStart;
    const context = parseSuggestionContext(rawValue, cursorIndex);
    if (!context) {
        return;
    }

    const prefixText = context.prefixModifier ? context.prefixModifier : '';
    const before = rawValue.slice(0, context.replaceStart);
    const after = rawValue.slice(context.replaceEnd);
    const replacement = `${prefixText}${suggestion}`;
    const nextValue = `${before}${replacement}${after}`;

    syncSearchInputValue(searchInput, nextValue);

    const nextCursor = before.length + replacement.length;
    if (typeof searchInput.setSelectionRange === 'function') {
        searchInput.setSelectionRange(nextCursor, nextCursor);
    }

    searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    searchInput.focus();
    hideSuggestions({ invalidateRequests: true });
}

function updateSelectedSuggestion(container) {
    const items = Array.from(container.querySelectorAll('.search-suggestion'));
    if (items.length === 0) {
        selectedIndex = -1;
        return;
    }
    if (selectedIndex < 0 || selectedIndex >= items.length) {
        selectedIndex = 0;
    }
    items.forEach((item, index) => {
        item.classList.toggle('is-selected', index === selectedIndex);
    });
}

function renderSuggestions(searchInput, suggestions) {
    const container = getSearchSuggestionsContainer();
    if (!Array.isArray(suggestions) || suggestions.length === 0) {
        hideSuggestions();
        return;
    }

    const items = suggestions
        .map((tag) => {
            if (typeof tag !== 'string') {
                throw new Error('Suggestion tags must be strings');
            }
            return `<button type="button" class="search-suggestion" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>`;
        })
        .join('');

    container.innerHTML = items;
    container.hidden = false;
    container.style.display = 'flex';
    selectedIndex = 0;
    updateSelectedSuggestion(container);

    container.querySelectorAll('.search-suggestion').forEach((button) => {
        button.addEventListener('mousedown', (event) => {
            if (event.button !== 0) {
                return;
            }
            event.preventDefault();
            const tag = button.dataset.tag;
            if (typeof tag !== 'string' || tag.length === 0) {
                throw new Error('Suggestion tag missing from dataset');
            }
            applySuggestion(searchInput, tag);
        });
    });
}

function normalizeUpdateOptions(options) {
    if (options === undefined) {
        return { source: 'programmatic' };
    }
    if (options === null || typeof options !== 'object') {
        throw new Error('updateSearchSuggestions options must be an object');
    }
    const source = options.source;
    if (source === undefined) {
        return { source: 'programmatic' };
    }
    if (typeof source !== 'string' || source.length === 0) {
        throw new Error('updateSearchSuggestions source must be a non-empty string');
    }
    return { source };
}

function doesUpdateSourceResumeSuggestions(source) {
    if (source === 'input') {
        return true;
    }
    if (source === 'search-input-click') {
        return true;
    }
    if (source === 'search-input-focus') {
        return true;
    }
    return false;
}

export function updateSearchSuggestions(searchInput, options) {
    if (!searchInput || typeof searchInput.value !== 'string') {
        throw new Error('updateSearchSuggestions requires search input element');
    }
    const updateOptions = normalizeUpdateOptions(options);
    if (doesUpdateSourceResumeSuggestions(updateOptions.source)) {
        suppressSuggestionsUntilInputInteraction = false;
    }
    if (document.activeElement !== searchInput) {
        if (pendingTimer) {
            clearTimeout(pendingTimer);
            pendingTimer = null;
        }
        requestSerial += 1;
        hideSuggestions();
        return;
    }
    if (suppressSuggestionsUntilInputInteraction) {
        clearPendingSuggestionRequest();
        hideSuggestions();
        return;
    }

    const rawValue = searchInput.value;
    const analysis = analyzeSearchQueryInput(rawValue);
    if (!analysis.isComplete && typeof analysis.warningMessage === 'string') {
        if (pendingTimer) {
            clearTimeout(pendingTimer);
            pendingTimer = null;
        }
        requestSerial += 1;
        hideSuggestions();
        return;
    }
    if (!Number.isInteger(searchInput.selectionStart)) {
        throw new Error('searchInput.selectionStart missing');
    }
    const cursorIndex = searchInput.selectionStart;
    const context = parseSuggestionContext(rawValue, cursorIndex);
    if (!context) {
        if (pendingTimer) {
            clearTimeout(pendingTimer);
            pendingTimer = null;
        }
        requestSerial += 1;
        hideSuggestions();
        return;
    }

    if (pendingTimer) {
        clearTimeout(pendingTimer);
    }

    const requestId = ++requestSerial;
    pendingTimer = setTimeout(async () => {
        pendingTimer = null;
        const response = await NotesAPI.fetchSearchSuggestions(
            rawValue,
            getSearchSuggestionWindowDays(),
        );
        if (!response || typeof response !== 'object') {
            throw new Error('Search suggestions response missing');
        }
        if (!Array.isArray(response.suggestions)) {
            throw new Error('Search suggestions response requires suggestions array');
        }
        if (requestId !== requestSerial) {
            return;
        }
        if (suppressSuggestionsUntilInputInteraction) {
            return;
        }
        renderSuggestions(searchInput, response.suggestions);
    }, SUGGESTION_DEBOUNCE_MS);
}

export function initializeSearchSuggestions() {
    const searchInput = document.getElementById('search-input');
    if (!searchInput || typeof searchInput.addEventListener !== 'function') {
        throw new Error('search-input element missing for suggestions');
    }

    const container = getSearchSuggestionsContainer();

    document.addEventListener('mousedown', (event) => {
        if (container.hidden) {
            return;
        }
        const target = event.target;
        if (!target || typeof target.closest !== 'function') {
            return;
        }
        if (target.closest('.search-controls')) {
            return;
        }
        hideSuggestions();
    }, true);

    searchInput.addEventListener('blur', () => {
        if (!container.hidden) {
            hideSuggestions();
        }
    });

    searchInput.addEventListener('focus', () => {
        updateSearchSuggestions(searchInput, { source: 'search-input-focus' });
    });

    searchInput.addEventListener('mousedown', () => {
        updateSearchSuggestions(searchInput, { source: 'search-input-click' });
    });

    searchInput.addEventListener('keydown', (event) => {
        if (container.hidden) {
            return;
        }
        const items = Array.from(container.querySelectorAll('.search-suggestion'));
        if (items.length === 0) {
            return;
        }
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
            updateSelectedSuggestion(container);
            return;
        }
        if (event.key === 'ArrowUp') {
            event.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, 0);
            updateSelectedSuggestion(container);
            return;
        }
        if (event.key === 'Enter') {
            event.preventDefault();
            event.stopPropagation();
            if (typeof event.stopImmediatePropagation === 'function') {
                event.stopImmediatePropagation();
            }
            let button = items[selectedIndex];
            if (!button) {
                button = items[0];
            }
            const tag = button.dataset.tag;
            if (typeof tag !== 'string' || tag.length === 0) {
                throw new Error('Suggestion tag missing from dataset');
            }
            applySuggestion(searchInput, tag);
        }
    });
}
