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
    constructor(readWindows, readShowWindowLabels, saveSettings) {
        super('searchSuggestionWindowsModal', 'search-suggestion-windows-modal');
        if (typeof readWindows !== 'function') {
            throw new Error('SearchSuggestionWindowsModal requires readWindows');
        }
        if (typeof readShowWindowLabels !== 'function') {
            throw new Error('SearchSuggestionWindowsModal requires readShowWindowLabels');
        }
        if (typeof saveSettings !== 'function') {
            throw new Error('SearchSuggestionWindowsModal requires saveSettings');
        }
        this._readWindows = readWindows;
        this._readShowWindowLabels = readShowWindowLabels;
        this._saveSettings = saveSettings;
    }

    getInitialModalState() {
        const showWindowLabels = this._readShowWindowLabels();
        if (typeof showWindowLabels !== 'boolean') {
            throw new Error('Search suggestion label preference must be boolean');
        }
        return {
            windowDays: validateSearchSuggestionWindows(this._readWindows()),
            showWindowLabels,
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
                <button type="button" class="secondary-btn search-window-remove"${disabled}>Remove</button>
            </div>
        `).join('');
        const emptyMessage = windowDays.length === 0
            ? '<p class="note-layout-description">No personalized slots. Base tag ordering will be used.</p>'
            : '';
        const error = typeof state.error === 'string' ? state.error : '';
        if (typeof state.showWindowLabels !== 'boolean') {
            throw new Error('Search suggestion modal label state must be boolean');
        }
        const showWindowLabelsChecked = state.showWindowLabels ? ' checked' : '';

        modalElement.innerHTML = `
            <div class="modal-content note-layout-appearance-modal-content">
                <h2>Search Suggestion Time Windows</h2>
                <p class="note-layout-description">Each ordered row controls one personalized suggestion slot. Activity is retained for the latest 365 populated days.</p>
                <div class="search-window-rows">${rows}</div>
                ${emptyMessage}
                <button type="button" class="secondary-btn" id="search-window-add-btn"${disabled}>Add slot</button>
                <label class="search-window-label-toggle">
                    <input type="checkbox" id="search-window-label-toggle"${showWindowLabelsChecked}${disabled}>
                    <span>Show time-window labels in search suggestions</span>
                </label>
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
            const removeButton = row.querySelector('.search-window-remove');
            if (!(input instanceof HTMLInputElement)) {
                throw new Error('Search window input missing');
            }
            if (!(removeButton instanceof HTMLButtonElement)) {
                throw new Error('Search window remove button missing');
            }
            input.onchange = () => this._changeWindow(index, input.value);
            removeButton.onclick = () => this._removeWindow(index);
        });

        const addButton = document.getElementById('search-window-add-btn');
        const labelToggle = document.getElementById('search-window-label-toggle');
        const saveButton = document.getElementById('search-window-save-btn');
        const cancelButton = document.getElementById('search-window-cancel-btn');
        if (!(addButton instanceof HTMLButtonElement)) {
            throw new Error('Search window add button missing');
        }
        if (!(labelToggle instanceof HTMLInputElement) || labelToggle.type !== 'checkbox') {
            throw new Error('Search window label checkbox missing');
        }
        if (!(saveButton instanceof HTMLButtonElement)) {
            throw new Error('Search window save button missing');
        }
        if (!(cancelButton instanceof HTMLButtonElement)) {
            throw new Error('Search window cancel button missing');
        }
        addButton.onclick = () => this._addWindow(windowDays);
        labelToggle.onchange = () => this.updateModalState({
            showWindowLabels: labelToggle.checked,
        });
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
        const showWindowLabels = this.getModalState().showWindowLabels;
        if (typeof showWindowLabels !== 'boolean') {
            throw new Error('Search suggestion label preference must be boolean');
        }
        this.updateModalState({ saving: true, error: '' });
        this.renderModalContent();
        await this._saveSettings(windowDays, showWindowLabels);
        this.close();
    }
}
