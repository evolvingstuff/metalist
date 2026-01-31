import { BaseModal } from './base-modal.js';

const ONTOLOGY_BASE = '/api2/ontology';
const TAG_LIMIT = 20;

function escapeHtml(value) {
    if (typeof value !== 'string') {
        throw new Error('escapeHtml requires a string');
    }
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function buildAuthHeaders() {
    const tabId = sessionStorage.getItem('metalist_tab_id');
    if (!tabId) {
        throw new Error('metalist_tab_id missing from sessionStorage');
    }

    const authToken = localStorage.getItem('auth_token');
    const headers = {
        'Content-Type': 'application/json',
        'X-Metalist-Tab-Id': tabId,
    };
    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }
    return headers;
}

async function fetchJson(url, options) {
    if (typeof url !== 'string') {
        throw new Error('fetchJson requires url string');
    }
    if (!options || typeof options !== 'object') {
        throw new Error('fetchJson requires options object');
    }

    const response = await fetch(url, options);
    if (response.ok) {
        return response.json();
    }

    const payload = await response.json().catch(() => null);
    if (payload && typeof payload.detail === 'string') {
        throw new Error(payload.detail);
    }
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
}

export class OntologyModal extends BaseModal {
    constructor() {
        super('ontologyModal', 'ontology-modal');
        this._abortController = null;

        this._handleSearchInput = this._handleSearchInput.bind(this);
        this._handleSearchKeydown = this._handleSearchKeydown.bind(this);
        this._handleClick = this._handleClick.bind(this);
    }

    getInitialModalState() {
        return {
            focusTag: '',
            searchQuery: '',
            tagsTotalCount: 0,
            tagsShownCount: 0,
            tags: [],
            focusView: null,
            error: null,
        };
    }

    onOpen() {
        document.body.classList.add('ontology-modal-open');
        this.renderSkeleton();
        void this.refreshTagSearch('');
    }

    onClose() {
        document.body.classList.remove('ontology-modal-open');
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }
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

        modalElement.innerHTML = `
            <div class="modal-content ontology-modal-content">
                <div class="ontology-modal-header">
                    <h2>Edit Tag Relationships</h2>
                    <button class="ontology-close" data-action="close" aria-label="Close">×</button>
                </div>

                <div class="ontology-search">
                    <input
                        type="text"
                        id="ontology-search-input"
                        placeholder="Search tags…"
                        autocomplete="off"
                    />
                    <div class="ontology-search-results" id="ontology-search-results"></div>
                </div>

                <div class="ontology-columns">
                    <section class="ontology-column" data-column="left">
                        <div class="ontology-column-title" id="ontology-left-title">Tags that imply</div>
                        <div class="ontology-list" id="ontology-left-list"></div>
                        <button class="ontology-add" data-action="add-left">+ Add more…</button>
                    </section>

                    <section class="ontology-column" data-column="middle">
                        <div class="ontology-column-title" id="ontology-middle-title">Focus</div>
                        <div class="ontology-list" id="ontology-middle-list"></div>
                        <button class="ontology-add" data-action="add-middle">+ Add synonym…</button>
                    </section>

                    <section class="ontology-column" data-column="right">
                        <div class="ontology-column-title" id="ontology-right-title">Tags implied by</div>
                        <div class="ontology-list" id="ontology-right-list"></div>
                        <button class="ontology-add" data-action="add-right">+ Add more…</button>
                    </section>
                </div>

                <div class="ontology-modal-footer">
                    <div id="ontology-counts">Showing 0 of 0 tags</div>
                    <div class="ontology-hints">esc to cancel • enter to focus</div>
                </div>
            </div>
        `;

        modalElement.style.display = 'block';
        modalElement.addEventListener('click', this._handleClick);

        const input = modalElement.querySelector('#ontology-search-input');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('ontology search input missing');
        }
        input.addEventListener('input', this._handleSearchInput);
        input.addEventListener('keydown', this._handleSearchKeydown);
        setTimeout(() => input.focus(), 50);
    }

    hideModalElement() {
        const modalElement = document.getElementById(this.modalElementId);
        if (modalElement) {
            modalElement.removeEventListener('click', this._handleClick);
        }
        super.hideModalElement();
    }

    renderSkeleton() {
        this.renderFocusView(null);
        this.renderTagSearchResults([]);
        this.renderCounts({ shown: 0, total: 0 });
    }

    renderCounts({ shown, total }) {
        if (!Number.isInteger(shown) || shown < 0) {
            throw new Error('renderCounts shown must be a non-negative integer');
        }
        if (!Number.isInteger(total) || total < 0) {
            throw new Error('renderCounts total must be a non-negative integer');
        }
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            return;
        }
        const target = modalElement.querySelector('#ontology-counts');
        if (target) {
            const suffix = total > shown ? '+' : '';
            target.textContent = `Showing ${shown} of ${total}${suffix} total tags`;
        }
    }

    _handleSearchInput(event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
            throw new Error('Expected ontology search input element');
        }
        const query = target.value;
        if (typeof query !== 'string') {
            throw new Error('Ontology search query must be a string');
        }
        this.updateModalState({ searchQuery: query });
        this.refreshTagSearch(query);
    }

    _handleSearchKeydown(event) {
        if (event.key !== 'Enter') {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        const state = this.getModalState();
        const query = state.searchQuery;
        if (typeof query !== 'string') {
            throw new Error('Modal searchQuery must be a string');
        }
        const trimmed = query.trim();
        if (trimmed === '') {
            return;
        }
        void this.setFocusTag(trimmed);
    }

    async refreshTagSearch(query) {
        if (typeof query !== 'string') {
            throw new Error('refreshTagSearch requires query string');
        }

        if (this._abortController) {
            this._abortController.abort();
        }
        const controller = new AbortController();
        this._abortController = controller;

        const trimmed = query.trim();
        const limit = trimmed === '' ? 0 : TAG_LIMIT;
        const url = `${ONTOLOGY_BASE}/tags?q=${encodeURIComponent(query)}&limit=${limit}`;

        await (async () => {
            const response = await fetch(url, {
                method: 'GET',
                headers: buildAuthHeaders(),
                signal: controller.signal,
            }).catch((error) => {
                if (error && error.name === 'AbortError') {
                    return null;
                }
                throw error;
            });

            if (response === null) {
                return;
            }

            if (!response.ok) {
                const payload = await response.json().catch(() => null);
                if (payload && typeof payload.detail === 'string') {
                    throw new Error(payload.detail);
                }
                throw new Error(`Request failed: ${response.status} ${response.statusText}`);
            }

            const payload = await response.json();
            if (this._abortController !== controller) {
                return;
            }

            const tags = payload.tags;
            const totalCount = payload.totalCount;
            if (!Array.isArray(tags)) {
                throw new Error('Ontology tags payload missing tags array');
            }
            if (!Number.isInteger(totalCount) || totalCount < 0) {
                throw new Error('Ontology tags payload missing totalCount');
            }

            this.updateModalState({
                tags,
                tagsTotalCount: totalCount,
                tagsShownCount: tags.length,
                error: null,
            });

            this.renderTagSearchResults(tags);
            this.renderCounts({ shown: tags.length, total: totalCount });
        })().catch((error) => {
            if (this._abortController !== controller) {
                return;
            }
            const message = error instanceof Error ? error.message : String(error);
            this.updateModalState({ error: message });
            this.renderTagSearchResults([]);
        }).finally(() => {
            if (this._abortController === controller) {
                this._abortController = null;
            }
        });
    }

    renderTagSearchResults(tags) {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            return;
        }
        const container = modalElement.querySelector('#ontology-search-results');
        if (!container) {
            return;
        }
        const query = this.getModalState().searchQuery;
        const trimmed = typeof query === 'string' ? query.trim() : '';
        if (trimmed === '' || !Array.isArray(tags) || tags.length === 0) {
            container.innerHTML = '';
            container.style.display = 'none';
            return;
        }

        container.innerHTML = tags
            .map((tag) => (
                `<button class="ontology-search-result" data-action="focus" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>`
            ))
            .join('');
        container.style.display = 'flex';
    }

    async setFocusTag(tag) {
        if (typeof tag !== 'string' || tag.trim() === '') {
            throw new Error('setFocusTag requires a non-empty string');
        }

        const normalized = tag.trim();
        const url = `${ONTOLOGY_BASE}/focus?tag=${encodeURIComponent(normalized)}`;

        await (async () => {
            const response = await fetch(url, {
                method: 'GET',
                headers: buildAuthHeaders(),
            });

            if (!response.ok) {
                const payload = await response.json().catch(() => null);
                if (payload && typeof payload.detail === 'string') {
                    throw new Error(payload.detail);
                }
                throw new Error(`Request failed: ${response.status} ${response.statusText}`);
            }

            const payload = await response.json();
            this.updateModalState({ focusTag: normalized, focusView: payload, error: null });
            this.renderFocusView(payload);
            this.renderTagSearchResults([]);
        })().catch((error) => {
            const message = error instanceof Error ? error.message : String(error);
            this.updateModalState({ error: message });
            this.renderFocusView(null);
            throw error;
        });
    }

    renderFocusView(view) {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            return;
        }

        const leftTitle = modalElement.querySelector('#ontology-left-title');
        const middleTitle = modalElement.querySelector('#ontology-middle-title');
        const rightTitle = modalElement.querySelector('#ontology-right-title');
        const leftList = modalElement.querySelector('#ontology-left-list');
        const middleList = modalElement.querySelector('#ontology-middle-list');
        const rightList = modalElement.querySelector('#ontology-right-list');
        if (!leftList || !middleList || !rightList || !leftTitle || !middleTitle || !rightTitle) {
            return;
        }

        if (!view) {
            leftTitle.textContent = 'Tags that imply';
            middleTitle.textContent = 'Focus';
            rightTitle.textContent = 'Tags implied by';
            leftList.innerHTML = '<div class="ontology-placeholder">Pick a focus tag…</div>';
            middleList.innerHTML = '';
            rightList.innerHTML = '';
            return;
        }

        const focusTag = view.focusTag;
        leftTitle.textContent = `Tags that imply '${focusTag}'`;
        middleTitle.textContent = `'${focusTag}' and synonyms`;
        rightTitle.textContent = `Tags that '${focusTag}' implies`;

        leftList.innerHTML = this._renderTagList(view.leftDirect, view.leftIndirect);
        middleList.innerHTML = this._renderMiddleList(view);
        rightList.innerHTML = this._renderTagList(view.rightDirect, view.rightIndirect);
    }

    _renderTagList(directRows, indirectTags) {
        if (!Array.isArray(directRows)) {
            throw new Error('directRows must be an array');
        }
        if (!Array.isArray(indirectTags)) {
            throw new Error('indirectTags must be an array');
        }

        const directHtml = directRows.map((row) => {
            const tag = row.tag;
            const ruleId = row.ruleId;
            if (typeof tag !== 'string') {
                throw new Error('direct tag must be string');
            }
            if (!Number.isInteger(ruleId) || ruleId < 0) {
                throw new Error('direct ruleId must be non-negative integer');
            }
            return `
                <div class="ontology-row">
                    <button class="ontology-tag" data-action="focus" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>
                    <button class="ontology-remove" data-action="remove" data-rule-id="${ruleId}" aria-label="Remove">−</button>
                </div>
            `;
        });

        const indirectHtml = indirectTags.map((tag) => {
            if (typeof tag !== 'string') {
                throw new Error('indirect tag must be string');
            }
            return `
                <div class="ontology-row">
                    <button class="ontology-tag" data-action="focus" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>
                    <span class="ontology-spacer"></span>
                </div>
            `;
        });

        const combined = directHtml.concat(indirectHtml);
        if (combined.length === 0) {
            return '<div class="ontology-placeholder">(none)</div>';
        }
        return combined.join('');
    }

    _renderMiddleList(view) {
        const focusTag = view.focusTag;
        if (typeof focusTag !== 'string') {
            throw new Error('focusTag must be string');
        }

        const equals = view.middle;
        if (!Array.isArray(equals)) {
            throw new Error('middle must be array');
        }

        const direct = view.middleDirect;
        if (!Array.isArray(direct)) {
            throw new Error('middleDirect must be array');
        }

        const directByTag = new Map();
        for (const row of direct) {
            const tag = row.tag;
            const ruleId = row.ruleId;
            if (typeof tag !== 'string') {
                throw new Error('middleDirect tag must be string');
            }
            if (!Number.isInteger(ruleId) || ruleId < 0) {
                throw new Error('middleDirect ruleId must be non-negative integer');
            }
            directByTag.set(tag, ruleId);
        }

        const rows = [];
        rows.push(`
            <div class="ontology-row ontology-focus">
                <button class="ontology-tag" data-action="focus" data-tag="${escapeHtml(focusTag)}">${escapeHtml(focusTag)}</button>
                <span class="ontology-spacer"></span>
            </div>
        `);

        for (const tag of equals) {
            if (tag === focusTag) {
                continue;
            }
            if (typeof tag !== 'string') {
                throw new Error('middle tag must be string');
            }

            const maybeRuleId = directByTag.get(tag);
            if (maybeRuleId !== undefined) {
                rows.push(`
                    <div class="ontology-row">
                        <button class="ontology-tag" data-action="focus" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>
                        <button class="ontology-remove" data-action="remove" data-rule-id="${maybeRuleId}" aria-label="Remove">−</button>
                    </div>
                `);
            } else {
                rows.push(`
                    <div class="ontology-row">
                        <button class="ontology-tag" data-action="focus" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>
                        <span class="ontology-spacer"></span>
                    </div>
                `);
            }
        }

        if (rows.length === 1) {
            rows.push('<div class="ontology-placeholder">(no synonyms)</div>');
        }
        return rows.join('');
    }

    async _createRule(text) {
        if (typeof text !== 'string' || text.trim() === '') {
            throw new Error('createRule requires non-empty text');
        }

        const payload = await fetchJson(`${ONTOLOGY_BASE}/rules`, {
            method: 'POST',
            headers: buildAuthHeaders(),
            body: JSON.stringify({ text }),
        });

        const id = payload.id;
        if (!Number.isInteger(id) || id < 0) {
            throw new Error('Invalid create rule response');
        }
    }

    async _deleteRule(ruleId) {
        if (!Number.isInteger(ruleId) || ruleId < 0) {
            throw new Error('deleteRule requires non-negative integer ruleId');
        }
        await fetchJson(`${ONTOLOGY_BASE}/rules/${ruleId}`, {
            method: 'DELETE',
            headers: buildAuthHeaders(),
        });
    }

    async _promptForTag(promptText) {
        if (typeof promptText !== 'string' || promptText.trim() === '') {
            throw new Error('promptText must be non-empty string');
        }
        const response = window.prompt(promptText);
        if (response === null) {
            return null;
        }
        if (typeof response !== 'string') {
            throw new Error('prompt must return string or null');
        }
        const trimmed = response.trim();
        if (trimmed === '') {
            return null;
        }
        return trimmed;
    }

    async _handleClick(event) {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        const action = target.dataset.action;
        if (typeof action !== 'string') {
            return;
        }

        if (action === 'close') {
            this.close();
            return;
        }

        if (action === 'focus') {
            const tag = target.dataset.tag;
            if (typeof tag !== 'string' || tag.trim() === '') {
                throw new Error('focus action missing tag');
            }
            void this.setFocusTag(tag);
            return;
        }

        if (action === 'remove') {
            const rawRuleId = target.dataset.ruleId;
            if (typeof rawRuleId !== 'string' || rawRuleId.trim() === '') {
                throw new Error('remove action missing ruleId');
            }
            const ruleId = Number.parseInt(rawRuleId, 10);
            if (!Number.isInteger(ruleId) || ruleId < 0) {
                throw new Error(`invalid rule id: ${rawRuleId}`);
            }

            await this._deleteRule(ruleId);
            const focusTag = this.getModalState().focusTag;
            if (typeof focusTag === 'string' && focusTag.trim() !== '') {
                await this.setFocusTag(focusTag);
            }
            return;
        }

        if (action === 'add-left' || action === 'add-right' || action === 'add-middle') {
            const state = this.getModalState();
            const focusTag = state.focusTag;
            if (typeof focusTag !== 'string' || focusTag.trim() === '') {
                throw new Error('Set a focus tag before editing relationships');
            }

            if (action === 'add-left') {
                const newTag = await this._promptForTag(`Tag that implies '${focusTag}':`);
                if (!newTag) {
                    return;
                }
                await this._createRule(`${newTag} => ${focusTag}`);
            } else if (action === 'add-right') {
                const newTag = await this._promptForTag(`Tag implied by '${focusTag}':`);
                if (!newTag) {
                    return;
                }
                await this._createRule(`${focusTag} => ${newTag}`);
            } else {
                const newTag = await this._promptForTag(`Synonym for '${focusTag}':`);
                if (!newTag) {
                    return;
                }
                await this._createRule(`${focusTag} = ${newTag}`);
            }

            await this.setFocusTag(focusTag);
        }
    }
}
