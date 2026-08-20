import { BaseModal } from './base-modal.js';
import {
    MAX_SEARCH_SUGGESTION_WINDOW_DAYS,
    MAX_SEARCH_SUGGESTION_WINDOW_SLOTS,
    getSearchSuggestionWindowsValidationError,
    validateSearchSuggestionWindows,
} from '../mode-manager/services/search-suggestion-windows-service.js';


function escapeHtml(value) {
    if (typeof value !== 'string') {
        throw new Error('escapeHtml requires string');
    }
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}


export class SearchSuggestionWindowsModal extends BaseModal {
    constructor(readWindows, saveWindows) {
        super('searchSuggestionWindowsModal', 'search-suggestion-windows-modal');
        if (typeof readWindows !== 'function') {
            throw new Error('SearchSuggestionWindowsModal requires readWindows');
        }
        if (typeof saveWindows !== 'function') {
            throw new Error('SearchSuggestionWindowsModal requires saveWindows');
        }
        this._readWindows = readWindows;
        this._saveWindows = saveWindows;
    }

    getInitialModalState() {
        return {
            windowDays: validateSearchSuggestionWindows(this._readWindows()),
            saving: false,
            error: '',
        };
    }

    showModalElement() {
        let modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            modalElement = document.createElement('div');
            modalElement.id = this.modalElementId;
            modalElement.className = 'modal';
            modalElement.style.display = 'none';
            document.body.appendChild(modalElement);
        }
        this.renderModalContent();
        modalElement.style.display = 'block';
        const firstInput = modalElement.querySelector('.search-window-days-input');
        if (firstInput instanceof HTMLInputElement) {
            firstInput.focus();
        }
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!(modalElement instanceof HTMLElement)) {
            throw new Error('Search suggestion windows modal element missing');
        }
        const state = this.getModalState();
        const windowDays = validateSearchSuggestionWindows(state.windowDays);
        const saving = state.saving === true;
        const disabled = saving ? ' disabled' : '';
        const rows = windowDays.map((dayCount, index) => `
            <div class="search-window-row" data-window-index="${index}">
                <span class="search-window-slot">Slot ${index + 1}</span>
                <input class="search-window-days-input" type="number" min="1" max="${MAX_SEARCH_SUGGESTION_WINDOW_DAYS}" value="${dayCount}" aria-label="Slot ${index + 1} window in days"${disabled}>
                <span>days</span>
                <button type="button" class="secondary-btn search-window-up" aria-label="Move slot ${index + 1} up"${index === 0 || saving ? ' disabled' : ''}>↑</button>
                <button type="button" class="secondary-btn search-window-down" aria-label="Move slot ${index + 1} down"${index === windowDays.length - 1 || saving ? ' disabled' : ''}>↓</button>
                <button type="button" class="secondary-btn search-window-remove"${disabled}>Remove</button>
            </div>
        `).join('');
        const emptyMessage = windowDays.length === 0
            ? '<p class="note-layout-description">No personalized slots. Base tag ordering will be used.</p>'
            : '';
        const error = typeof state.error === 'string' ? state.error : '';

        modalElement.innerHTML = `
            <div class="modal-content note-layout-appearance-modal-content">
                <h2>Search Suggestion Time Windows</h2>
                <p class="note-layout-description">Each ordered row controls one personalized suggestion slot. Activity is retained for the latest 365 populated days.</p>
                <div class="search-window-rows">${rows}</div>
                ${emptyMessage}
                <button type="button" class="secondary-btn" id="search-window-add-btn"${disabled}>Add slot</button>
                <div class="form-actions">
                    <button type="button" class="primary-btn" id="search-window-save-btn" data-modal-enter-action${disabled}>${saving ? 'Saving…' : 'Save'}</button>
                    <button type="button" class="secondary-btn" id="search-window-cancel-btn"${disabled}>Cancel</button>
                </div>
                <p class="error-message">${escapeHtml(error)}</p>
            </div>
        `;
        this._bindControls(windowDays);
    }

    _bindControls(windowDays) {
        const modalElement = document.getElementById(this.modalElementId);
        if (!(modalElement instanceof HTMLElement)) {
            throw new Error('Search suggestion windows modal element missing');
        }
        const rows = Array.from(modalElement.querySelectorAll('.search-window-row'));
        rows.forEach((row, index) => {
            const input = row.querySelector('.search-window-days-input');
            const upButton = row.querySelector('.search-window-up');
            const downButton = row.querySelector('.search-window-down');
            const removeButton = row.querySelector('.search-window-remove');
            if (!(input instanceof HTMLInputElement)) {
                throw new Error('Search window input missing');
            }
            if (!(upButton instanceof HTMLButtonElement)) {
                throw new Error('Search window up button missing');
            }
            if (!(downButton instanceof HTMLButtonElement)) {
                throw new Error('Search window down button missing');
            }
            if (!(removeButton instanceof HTMLButtonElement)) {
                throw new Error('Search window remove button missing');
            }
            input.onchange = () => this._changeWindow(index, input.value);
            upButton.onclick = () => this._moveWindow(index, -1);
            downButton.onclick = () => this._moveWindow(index, 1);
            removeButton.onclick = () => this._removeWindow(index);
        });

        const addButton = document.getElementById('search-window-add-btn');
        const saveButton = document.getElementById('search-window-save-btn');
        const cancelButton = document.getElementById('search-window-cancel-btn');
        if (!(addButton instanceof HTMLButtonElement)) {
            throw new Error('Search window add button missing');
        }
        if (!(saveButton instanceof HTMLButtonElement)) {
            throw new Error('Search window save button missing');
        }
        if (!(cancelButton instanceof HTMLButtonElement)) {
            throw new Error('Search window cancel button missing');
        }
        addButton.onclick = () => this._addWindow(windowDays);
        saveButton.onclick = async () => this._handleSave();
        cancelButton.onclick = () => this.close();
    }

    _changeWindow(index, rawValue) {
        const dayCount = Number(rawValue);
        const next = this.getModalState().windowDays.slice();
        next[index] = dayCount;
        const validationError = getSearchSuggestionWindowsValidationError(next);
        if (validationError === '') {
            this.updateModalState({ windowDays: next, error: '' });
        } else {
            this.updateModalState({ error: validationError });
        }
        this.renderModalContent();
    }

    _moveWindow(index, offset) {
        const next = this.getModalState().windowDays.slice();
        const target = index + offset;
        if (target < 0 || target >= next.length) {
            throw new Error('Search window move target is out of range');
        }
        [next[index], next[target]] = [next[target], next[index]];
        this.updateModalState({ windowDays: next, error: '' });
        this.renderModalContent();
    }

    _removeWindow(index) {
        const next = this.getModalState().windowDays.slice();
        next.splice(index, 1);
        this.updateModalState({ windowDays: next, error: '' });
        this.renderModalContent();
    }

    _addWindow(windowDays) {
        if (windowDays.length >= MAX_SEARCH_SUGGESTION_WINDOW_SLOTS) {
            throw new Error(
                `Search suggestion windows cannot contain more than ${MAX_SEARCH_SUGGESTION_WINDOW_SLOTS} slots`,
            );
        }
        const used = new Set(windowDays);
        let nextValue = 1;
        while (used.has(nextValue) && nextValue <= MAX_SEARCH_SUGGESTION_WINDOW_DAYS) {
            nextValue += 1;
        }
        if (nextValue > MAX_SEARCH_SUGGESTION_WINDOW_DAYS) {
            throw new Error('All supported search suggestion windows are already in use');
        }
        this.updateModalState({ windowDays: [...windowDays, nextValue], error: '' });
        this.renderModalContent();
    }

    async _handleSave() {
        const windowDays = validateSearchSuggestionWindows(this.getModalState().windowDays);
        this.updateModalState({ saving: true, error: '' });
        this.renderModalContent();
        await this._saveWindows(windowDays);
        this.close();
    }
}
