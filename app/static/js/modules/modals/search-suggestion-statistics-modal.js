import { BaseModal } from './base-modal.js';
import {
    validateSearchSuggestionStatistics,
} from '../mode-manager/services/search-suggestion-statistics-service.js';
import {
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


function pluralize(count, singular, plural) {
    if (!Number.isInteger(count) || count < 0) {
        throw new Error('pluralize requires a non-negative integer');
    }
    return count === 1 ? singular : plural;
}


export class SearchSuggestionStatisticsModal extends BaseModal {
    constructor(loadStatistics, readWindows) {
        super('searchSuggestionStatisticsModal', 'search-suggestion-statistics-modal');
        if (typeof loadStatistics !== 'function') {
            throw new Error('SearchSuggestionStatisticsModal requires loadStatistics');
        }
        if (typeof readWindows !== 'function') {
            throw new Error('SearchSuggestionStatisticsModal requires readWindows');
        }
        this._loadStatistics = loadStatistics;
        this._readWindows = readWindows;
        this._loadGeneration = 0;
    }

    getInitialModalState() {
        return {
            loading: true,
            statistics: null,
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
    }

    async onOpen() {
        this._loadGeneration += 1;
        const loadGeneration = this._loadGeneration;
        const statistics = validateSearchSuggestionStatistics(await this._loadStatistics());
        if (!this.isOpen || loadGeneration !== this._loadGeneration) {
            return;
        }
        this.updateModalState({ loading: false, statistics });
        this.renderModalContent();
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!(modalElement instanceof HTMLElement)) {
            throw new Error('Search suggestion statistics modal element missing');
        }
        const state = this.getModalState();
        const windowDays = validateSearchSuggestionWindows(this._readWindows());
        const windowText = windowDays.length === 0
            ? 'None (personalization disabled)'
            : windowDays.map((dayCount) => `${dayCount}d`).join(' → ');
        let body = '<p class="search-suggestion-statistics-status">Loading statistics…</p>';
        if (state.loading !== true) {
            body = this._buildStatisticsHtml(
                validateSearchSuggestionStatistics(state.statistics),
            );
        }

        modalElement.innerHTML = `
            <div class="modal-content search-suggestion-statistics-modal-content">
                <h2>Search Suggestion Statistics</h2>
                <p class="note-layout-description">Each qualifying note interaction credits every distinct raw tag on that note once, including inherited and meta tags. Search text and note contents are not collected.</p>
                <p class="search-suggestion-statistics-windows"><strong>Configured slots:</strong> ${escapeHtml(windowText)}</p>
                ${body}
                <div class="form-actions">
                    <button type="button" class="primary-btn" id="search-suggestion-statistics-close-btn" data-modal-enter-action>Close</button>
                </div>
            </div>
        `;
        const closeButton = document.getElementById('search-suggestion-statistics-close-btn');
        if (!(closeButton instanceof HTMLButtonElement)) {
            throw new Error('Search suggestion statistics close button missing');
        }
        closeButton.onclick = () => this.close();
    }

    _buildStatisticsHtml(statistics) {
        if (statistics.days.length === 0) {
            return '<p class="search-suggestion-statistics-empty">No search-suggestion activity has been collected.</p>';
        }
        const populatedDayCount = statistics.days.length;
        const daySections = statistics.days.map((day, index) => `
            <details class="search-suggestion-statistics-day"${index === 0 ? ' open' : ''}>
                <summary>
                    <span>${escapeHtml(day.date)}</span>
                    <span>${day.totalTagCredits} ${pluralize(day.totalTagCredits, 'tag credit', 'tag credits')}</span>
                </summary>
                <table class="search-suggestion-statistics-table">
                    <thead><tr><th scope="col">Tag</th><th scope="col">Credits</th></tr></thead>
                    <tbody>
                        ${day.tags.map((entry) => `
                            <tr><td>${escapeHtml(entry.tag)}</td><td>${entry.count}</td></tr>
                        `).join('')}
                    </tbody>
                </table>
            </details>
        `).join('');
        return `
            <p class="search-suggestion-statistics-retention">${populatedDayCount} populated ${pluralize(populatedDayCount, 'day', 'days')} retained (maximum ${statistics.retentionPopulatedDayLimit}).</p>
            <div class="search-suggestion-statistics-days">${daySections}</div>
        `;
    }
}
