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

function escapeQuotedPhrase(phrase) {
    if (typeof phrase !== 'string') {
        throw new Error('escapeQuotedPhrase requires string');
    }
    return phrase.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function escapeRegexPattern(pattern) {
    if (typeof pattern !== 'string') {
        throw new Error('escapeRegexPattern requires string');
    }
    return pattern.replace(/\\/g, '\\\\').replace(/\//g, '\\/');
}

function isValidTagToken(token) {
    if (typeof token !== 'string') {
        throw new Error('isValidTagToken requires string');
    }
    if (token.trim() !== token) {
        return false;
    }
    if (token.length === 0) {
        return false;
    }
    if (/\s/.test(token)) {
        return false;
    }
    if (token.startsWith('-') || token.startsWith('+') || token.startsWith('/')) {
        return false;
    }
    if (token.startsWith('"') || token.startsWith("'")) {
        return false;
    }
    if (token.startsWith('(') || token.startsWith(')')) {
        return false;
    }
    if (token.includes('#')) {
        return false;
    }

    const disallowed = new Set([':', '"', '\\', '>', '<', '=', '[', ']', '{', '}', '(', ')', '*', '|', ';', '~', '`']);
    for (const ch of token) {
        if (disallowed.has(ch)) {
            return false;
        }
    }
    return true;
}

function parseIncomingAtoms(raw) {
    if (typeof raw !== 'string') {
        throw new Error('parseIncomingAtoms requires string');
    }

    const atoms = [];
    let index = 0;
    while (index < raw.length) {
        while (index < raw.length && raw[index].match(/\s/)) {
            index += 1;
        }
        if (index >= raw.length) {
            break;
        }
        const ch = raw[index];
        if (ch === '(' || ch === ')') {
            index += 1;
            continue;
        }
        if (ch === '"' || ch === "'") {
            const quote = ch;
            let token = quote;
            index += 1;
            while (index < raw.length) {
                const c = raw[index];
                token += c;
                if (c === '\\') {
                    if (index + 1 < raw.length) {
                        token += raw[index + 1];
                        index += 2;
                        continue;
                    }
                    index += 1;
                    continue;
                }
                if (c === quote) {
                    index += 1;
                    break;
                }
                index += 1;
            }
            if (token.length < 2 || token[token.length - 1] !== quote) {
                throw new Error(`Unclosed quote: ${quote}`);
            }
            atoms.push(token);
            continue;
        }
        if (ch === '/') {
            let token = '/';
            index += 1;
            while (index < raw.length) {
                const c = raw[index];
                token += c;
                if (c === '\\') {
                    if (index + 1 < raw.length) {
                        token += raw[index + 1];
                        index += 2;
                        continue;
                    }
                    index += 1;
                    continue;
                }
                if (c === '/') {
                    index += 1;
                    break;
                }
                index += 1;
            }
            if (token[token.length - 1] !== '/') {
                throw new Error('Unclosed regex literal');
            }

            let flags = '';
            while (index < raw.length) {
                const c = raw[index];
                if (c.match(/\s/) || c === ')') {
                    break;
                }
                flags += c;
                index += 1;
            }
            if (flags !== '' && flags !== 'i') {
                throw new Error(`Unsupported regex flags: ${flags}`);
            }
            atoms.push(token + flags);
            continue;
        }

        const start = index;
        while (index < raw.length) {
            const c = raw[index];
            if (c.match(/\s/) || c === '(' || c === ')') {
                break;
            }
            index += 1;
        }
        const token = raw.slice(start, index);
        if (token === '=>' || token === '=') {
            throw new Error('Do not include operators; only enter the condition.');
        }
        if (token !== '') {
            atoms.push(token);
        }
    }

    return atoms;
}

function renderIncomingAtoms(atoms) {
    if (!Array.isArray(atoms)) {
        throw new Error('renderIncomingAtoms requires array');
    }
    const parts = [];
    for (const atom of atoms) {
        if (!atom || typeof atom !== 'object') {
            throw new Error('incoming atom must be object');
        }
        const kind = atom.kind;
        if (typeof kind !== 'string' || kind.trim() === '') {
            throw new Error('incoming atom missing kind');
        }

        if (kind === 'tag') {
            const tag = atom.tag;
            if (typeof tag !== 'string' || tag.trim() === '') {
                throw new Error('incoming tag atom missing tag');
            }
            parts.push(
                `<button class="ontology-atom ontology-atom-tag" data-action="focus" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>`
            );
            continue;
        }

        if (kind === 'text') {
            const text = atom.text;
            if (typeof text !== 'string' || text.trim() === '') {
                throw new Error('incoming text atom missing text');
            }
            parts.push(`<span class="ontology-atom ontology-atom-text">${escapeHtml(text)}</span>`);
            continue;
        }

        if (kind === 'regex') {
            const regex = atom.regex;
            if (typeof regex !== 'string' || regex.trim() === '') {
                throw new Error('incoming regex atom missing regex');
            }
            parts.push(`<span class="ontology-atom ontology-atom-regex">${escapeHtml(regex)}</span>`);
            continue;
        }

        throw new Error(`Unknown incoming atom kind: ${kind}`);
    }

    return parts.join('<span class="ontology-atom-sep"> </span>');
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
        this._rulesCache = null;

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

        this._rulesCache = null;
    }

    focusSearchInput() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            return;
        }
        const input = modalElement.querySelector('#ontology-search-input');
        if (!(input instanceof HTMLInputElement)) {
            return;
        }
        input.focus();
        input.select();
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

                <div class="ontology-error" id="ontology-error" style="display:none"></div>

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
        this.renderError(null);
    }

    renderError(message) {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            return;
        }
        const target = modalElement.querySelector('#ontology-error');
        if (!target) {
            return;
        }

        if (message === null) {
            target.textContent = '';
            target.style.display = 'none';
            return;
        }
        if (typeof message !== 'string' || message.trim() === '') {
            throw new Error('renderError requires string or null');
        }

        target.textContent = message;
        target.style.display = 'block';
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

        leftList.innerHTML = this._renderIncomingRules(view);
        middleList.innerHTML = this._renderMiddleList(view);
        rightList.innerHTML = this._renderTagList(view.rightDirect, view.rightIndirect);
    }

    _renderIncomingRules(view) {
        const incoming = view.incomingRules;
        const indirectTags = view.leftIndirect;
        if (!Array.isArray(incoming)) {
            throw new Error('incomingRules must be array');
        }
        if (!Array.isArray(indirectTags)) {
            throw new Error('leftIndirect must be array');
        }

        const directHtml = incoming.map((rule) => {
            const ruleId = rule.id;
            const kind = rule.kind;
            const display = rule.display;
            const lhsAtoms = rule.lhsAtoms;
            const lhsTag = rule.lhsTag;
            if (!Number.isInteger(ruleId) || ruleId < 0) {
                throw new Error('incoming rule id must be non-negative integer');
            }
            if (typeof kind !== 'string' || kind.trim() === '') {
                throw new Error('incoming rule kind must be non-empty string');
            }
            if (typeof display !== 'string' || display.trim() === '') {
                throw new Error('incoming rule display must be non-empty string');
            }
            if (!Array.isArray(lhsAtoms) || lhsAtoms.length === 0) {
                throw new Error('incoming rule lhsAtoms must be non-empty array');
            }
            if (lhsTag !== null && typeof lhsTag !== 'string') {
                throw new Error('incoming rule lhsTag must be string or null');
            }

            const lhs = renderIncomingAtoms(lhsAtoms);

            return `
                <div class="ontology-row">
                    <div class="ontology-rule-left">
                        ${lhs}
                    </div>
                    <div class="ontology-row-actions">
                        <button class="ontology-edit" data-action="edit-incoming" data-rule-id="${ruleId}" aria-label="Edit">✎</button>
                        <button class="ontology-remove" data-action="remove" data-rule-ids="${ruleId}" aria-label="Remove">−</button>
                    </div>
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

        const combined = [];
        if (directHtml.length === 0) {
            combined.push('<div class="ontology-placeholder">(no direct rules)</div>');
        } else {
            combined.push(...directHtml);
        }
        if (directHtml.length > 0 && indirectHtml.length > 0) {
            combined.push('<div class="ontology-divider"></div>');
        }
        combined.push(...indirectHtml);

        if (combined.length === 0) {
            return '<div class="ontology-placeholder">(none)</div>';
        }
        return combined.join('');
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
            const ruleIds = row.ruleIds;
            if (typeof tag !== 'string') {
                throw new Error('direct tag must be string');
            }
            if (!Array.isArray(ruleIds) || ruleIds.length === 0) {
                throw new Error('direct ruleIds must be non-empty array');
            }
            for (const ruleId of ruleIds) {
                if (!Number.isInteger(ruleId) || ruleId < 0) {
                    throw new Error('direct ruleId must be non-negative integer');
                }
            }

            const ruleIdsAttr = ruleIds.join(',');
            const canEdit = ruleIds.length === 1;
            return `
                <div class="ontology-row">
                    <button class="ontology-tag" data-action="focus" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>
                    <div class="ontology-row-actions">
                        ${canEdit ? `<button class="ontology-edit" data-action="edit" data-rule-id="${ruleIds[0]}" aria-label="Edit">✎</button>` : ''}
                        <button class="ontology-remove" data-action="remove" data-rule-ids="${ruleIdsAttr}" aria-label="Remove">−</button>
                    </div>
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

        const combined = [];
        combined.push(...directHtml);
        if (directHtml.length > 0 && indirectHtml.length > 0) {
            combined.push('<div class="ontology-divider"></div>');
        }
        combined.push(...indirectHtml);
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
            const ruleIds = row.ruleIds;
            if (typeof tag !== 'string') {
                throw new Error('middleDirect tag must be string');
            }
            if (!Array.isArray(ruleIds) || ruleIds.length === 0) {
                throw new Error('middleDirect ruleIds must be non-empty array');
            }
            for (const ruleId of ruleIds) {
                if (!Number.isInteger(ruleId) || ruleId < 0) {
                    throw new Error('middleDirect ruleId must be non-negative integer');
                }
            }
            directByTag.set(tag, ruleIds);
        }

        const rows = [];
        rows.push(`
            <div class="ontology-row ontology-focus">
                <button class="ontology-tag" data-action="focus" data-tag="${escapeHtml(focusTag)}">${escapeHtml(focusTag)}</button>
                <div class="ontology-row-actions">
                    <button class="ontology-edit" data-action="rename-focus" aria-label="Rename">✎</button>
                    <span class="ontology-spacer"></span>
                </div>
            </div>
        `);

        for (const tag of equals) {
            if (tag === focusTag) {
                continue;
            }
            if (typeof tag !== 'string') {
                throw new Error('middle tag must be string');
            }

            const maybeRuleIds = directByTag.get(tag);
            if (maybeRuleIds !== undefined) {
                const ruleIdsAttr = maybeRuleIds.join(',');
                const canEdit = maybeRuleIds.length === 1;
                rows.push(`
                    <div class="ontology-row">
                        <button class="ontology-tag" data-action="focus" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>
                        <div class="ontology-row-actions">
                            ${canEdit ? `<button class="ontology-edit" data-action="edit" data-rule-id="${maybeRuleIds[0]}" aria-label="Edit">✎</button>` : ''}
                            <button class="ontology-remove" data-action="remove" data-rule-ids="${ruleIdsAttr}" aria-label="Remove">−</button>
                        </div>
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

        this._rulesCache = null;
    }

    async _loadRulesCache() {
        if (this._rulesCache !== null) {
            return this._rulesCache;
        }

        const response = await fetch(`${ONTOLOGY_BASE}/rules`, {
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
        const rules = payload.rules;
        if (!Array.isArray(rules)) {
            throw new Error('rules payload missing rules array');
        }
        const map = new Map();
        for (const rule of rules) {
            const id = rule.id;
            const text = rule.text;
            if (!Number.isInteger(id) || id < 0) {
                throw new Error('invalid rule id from server');
            }
            if (typeof text !== 'string') {
                throw new Error('invalid rule text from server');
            }
            map.set(id, text);
        }
        this._rulesCache = map;
        return map;
    }

    async _editRule(ruleId) {
        if (!Number.isInteger(ruleId) || ruleId < 0) {
            throw new Error('editRule requires non-negative integer ruleId');
        }

        const rules = await this._loadRulesCache();
        const existing = rules.get(ruleId);
        if (typeof existing !== 'string') {
            throw new Error(`Unknown rule id: ${ruleId}`);
        }

        const next = window.prompt('Edit rule:', existing);
        if (next === null) {
            return;
        }
        if (typeof next !== 'string') {
            throw new Error('prompt must return string or null');
        }
        if (next.trim() === '') {
            return;
        }

        await fetchJson(`${ONTOLOGY_BASE}/rules/${ruleId}`, {
            method: 'PUT',
            headers: buildAuthHeaders(),
            body: JSON.stringify({ text: next }),
        });
        this._rulesCache = null;
    }

    async _editIncomingRule(ruleId) {
        if (!Number.isInteger(ruleId) || ruleId < 0) {
            throw new Error('editIncomingRule requires non-negative integer ruleId');
        }

        const state = this.getModalState();
        const focusView = state.focusView;
        if (!focusView || typeof focusView !== 'object') {
            throw new Error('focusView missing');
        }
        const incoming = focusView.incomingRules;
        if (!Array.isArray(incoming)) {
            throw new Error('focusView.incomingRules must be array');
        }
        const match = incoming.find((rule) => rule && typeof rule === 'object' && rule.id === ruleId);
        if (!match) {
            throw new Error(`Unknown rule id: ${ruleId}`);
        }

        const kind = match.kind;
        const rhs = match.rhs;
        const editValue = match.editValue;

        if (typeof kind !== 'string' || kind.trim() === '') {
            throw new Error('incoming rule kind missing');
        }
        if (typeof rhs !== 'string' || rhs.trim() === '') {
            throw new Error('incoming rule rhs missing');
        }
        if (typeof editValue !== 'string') {
            throw new Error('incoming rule editValue missing');
        }

        if (kind !== 'tag' && kind !== 'text' && kind !== 'regex' && kind !== 'and') {
            throw new Error(`Unknown incoming rule kind: ${kind}`);
        }

        const promptValue = typeof editValue === 'string' ? editValue : '';
        const raw = window.prompt(`Condition that implies '${rhs}' (no =>, no parentheses required):`, promptValue);
        if (raw === null) {
            return;
        }
        if (typeof raw !== 'string') {
            throw new Error('prompt must return string or null');
        }

        const trimmed = raw.trim();
        if (trimmed === '') {
            return;
        }

        const atoms = parseIncomingAtoms(trimmed);
        if (atoms.length === 0) {
            return;
        }

        let updatedText = null;
        if (atoms.length === 1) {
            updatedText = `${atoms[0]} => ${rhs}`;
        } else {
            updatedText = `(${atoms.join(' ')}) => ${rhs}`;
        }

        await fetchJson(`${ONTOLOGY_BASE}/rules/${ruleId}`, {
            method: 'PUT',
            headers: buildAuthHeaders(),
            body: JSON.stringify({ text: updatedText }),
        });
        this._rulesCache = null;

        const focusTag = state.focusTag;
        if (typeof focusTag === 'string' && focusTag.trim() !== '') {
            await this.setFocusTag(focusTag);
        }
    }

    async _renameFocusedTag() {
        const state = this.getModalState();
        const focusTag = state.focusTag;
        if (typeof focusTag !== 'string' || focusTag.trim() === '') {
            throw new Error('Focus tag missing');
        }

        const next = window.prompt('Rename tag (rules only):', focusTag);
        if (next === null) {
            return;
        }
        if (typeof next !== 'string') {
            throw new Error('prompt must return string or null');
        }
        const trimmed = next.trim();
        if (trimmed === '' || trimmed === focusTag) {
            return;
        }

        const confirmed = window.confirm(
            `Rename tag '${focusTag}' → '${trimmed}' in ontology_rules.txt?\n\n` +
            'This renames the tag in BOTH ontology rules and all note tag bars.\n' +
            'This cannot be undone automatically.'
        );
        if (!confirmed) {
            return;
        }

        await fetchJson(`${ONTOLOGY_BASE}/rename-tag`, {
            method: 'POST',
            headers: buildAuthHeaders(),
            body: JSON.stringify({ old: focusTag, new: trimmed }),
        });
        this._rulesCache = null;
        await this.setFocusTag(trimmed);
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

    async _deleteRules(ruleIds) {
        if (!Array.isArray(ruleIds) || ruleIds.length === 0) {
            throw new Error('deleteRules requires non-empty array');
        }
        for (const ruleId of ruleIds) {
            if (!Number.isInteger(ruleId) || ruleId < 0) {
                throw new Error('deleteRules requires non-negative integer ids');
            }
        }

        for (const ruleId of ruleIds) {
            await this._deleteRule(ruleId);
        }
        this._rulesCache = null;
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

    async _promptForSingleTagToken(promptText) {
        const response = await this._promptForTag(promptText);
        if (!response) {
            return null;
        }

        const trimmed = response.trim();
        if (!isValidTagToken(trimmed)) {
            throw new Error(
                'That input is not a valid tag token. ' +
                'This action only supports a single tag (no spaces, quotes, regex, or parentheses).'
            );
        }
        return trimmed;
    }

    async _promptForIncomingRule(focusTag) {
        if (typeof focusTag !== 'string' || focusTag.trim() === '') {
            throw new Error('focusTag must be non-empty string');
        }

        const raw = window.prompt(
            `Condition that implies '${focusTag}' (no =>, no parentheses required):\n` +
            `- Tag: smart-guy\n` +
            `- Text: "asdf"\n` +
            `- Regex: /foo.*/i\n` +
            `- AND: "asdf" bbbb`,
            ''
        );
        if (raw === null) {
            return null;
        }
        if (typeof raw !== 'string') {
            throw new Error('prompt must return string or null');
        }
        const trimmed = raw.trim();
        if (trimmed === '') {
            return null;
        }

        const atoms = parseIncomingAtoms(trimmed);
        if (atoms.length === 0) {
            return null;
        }

        if (atoms.length === 1) {
            return `${atoms[0]} => ${focusTag}`;
        }
        return `(${atoms.join(' ')}) => ${focusTag}`;
    }

    async _handleClick(event) {
        await (async () => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) {
                return;
            }
            const action = target.dataset.action;
            if (typeof action !== 'string') {
                return;
            }

            this.renderError(null);

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

            if (action === 'rename-focus') {
                await this._renameFocusedTag();
                return;
            }

            if (action === 'remove') {
            const rawRuleIds = target.dataset.ruleIds;
            if (typeof rawRuleIds !== 'string' || rawRuleIds.trim() === '') {
                throw new Error('remove action missing ruleIds');
            }
            const ruleIds = rawRuleIds
                .split(',')
                .map((value) => value.trim())
                .filter((value) => value !== '')
                .map((value) => Number.parseInt(value, 10));
            if (ruleIds.length === 0) {
                throw new Error('remove action missing ruleIds');
            }
            for (const ruleId of ruleIds) {
                if (!Number.isInteger(ruleId) || ruleId < 0) {
                    throw new Error(`invalid rule id: ${rawRuleIds}`);
                }
            }

            const confirmed = window.confirm(
                ruleIds.length === 1
                    ? `Delete rule ${ruleIds[0]}? This cannot be undone.`
                    : `Delete ${ruleIds.length} rules (${ruleIds.join(', ')})? This cannot be undone.`
            );
            if (!confirmed) {
                return;
            }

            await this._deleteRules(ruleIds);
            const focusTag = this.getModalState().focusTag;
            if (typeof focusTag === 'string' && focusTag.trim() !== '') {
                await this.setFocusTag(focusTag);
            }
                return;
            }

            if (action === 'edit') {
            const rawRuleId = target.dataset.ruleId;
            if (typeof rawRuleId !== 'string' || rawRuleId.trim() === '') {
                throw new Error('edit action missing ruleId');
            }
            const ruleId = Number.parseInt(rawRuleId, 10);
            if (!Number.isInteger(ruleId) || ruleId < 0) {
                throw new Error(`invalid rule id: ${rawRuleId}`);
            }

            await this._editRule(ruleId);
            const focusTag = this.getModalState().focusTag;
            if (typeof focusTag === 'string' && focusTag.trim() !== '') {
                await this.setFocusTag(focusTag);
            }
                return;
            }

            if (action === 'edit-incoming') {
            const rawRuleId = target.dataset.ruleId;
            if (typeof rawRuleId !== 'string' || rawRuleId.trim() === '') {
                throw new Error('edit action missing ruleId');
            }
            const ruleId = Number.parseInt(rawRuleId, 10);
            if (!Number.isInteger(ruleId) || ruleId < 0) {
                throw new Error(`invalid rule id: ${rawRuleId}`);
            }

            await this._editIncomingRule(ruleId);
                return;
            }

            if (action === 'add-left' || action === 'add-right' || action === 'add-middle') {
            const state = this.getModalState();
            const focusTag = state.focusTag;
            if (typeof focusTag !== 'string' || focusTag.trim() === '') {
                throw new Error('Set a focus tag before editing relationships');
            }

            if (action === 'add-left') {
                const ruleText = await this._promptForIncomingRule(focusTag);
                if (!ruleText) {
                    return;
                }
                await this._createRule(ruleText);
            } else if (action === 'add-right') {
                const newTag = await this._promptForSingleTagToken(
                    `Tag implied by '${focusTag}' (single token only):`
                );
                if (!newTag) {
                    return;
                }
                await this._createRule(`${focusTag} => ${newTag}`);
            } else {
                const newTag = await this._promptForSingleTagToken(
                    `Synonym for '${focusTag}' (single token only):`
                );
                if (!newTag) {
                    return;
                }
                await this._createRule(`${focusTag} = ${newTag}`);
            }

            await this.setFocusTag(focusTag);
            }
        })().catch((error) => {
            const message = error instanceof Error ? error.message : String(error);
            console.error('Ontology modal action failed', error);
            this.renderError(
                message +
                (message.includes('single tag')
                    ? ' Use the LEFT column for text/regex/AND matchers.'
                    : '')
            );
        });
    }
}
