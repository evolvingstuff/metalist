import { BaseModal } from './base-modal.js';
import { CommandGate } from '../mode-manager/services/command-gate-service.js';

const ONTOLOGY_BASE = '/api2/ontology';
const TAG_LIMIT = 20;
const DIALOG_SUGGESTION_LIMIT = 8;
const DIALOG_SUGGESTION_DEBOUNCE_MS = 50;

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
    const disallowed = new Set([':', '"', '\\', '>', '<', '=', '[', ']', '{', '}', '(', ')', '*', '|', ';', '~', '`']);
    for (const ch of token) {
        if (disallowed.has(ch)) {
            return false;
        }
    }
    return true;
}

function isSuggestionSeparator(ch) {
    if (typeof ch !== 'string' || ch.length !== 1) {
        throw new Error('isSuggestionSeparator requires single character');
    }
    if (/\s/.test(ch)) {
        return true;
    }
    if (ch === '(' || ch === ')' || ch === '=' || ch === '>') {
        return true;
    }
    return false;
}

function isValidTagPrefix(prefix) {
    if (typeof prefix !== 'string') {
        throw new Error('isValidTagPrefix requires string');
    }
    if (prefix === '') {
        return true;
    }
    return isValidTagToken(prefix);
}

function parseDialogSuggestionContext(rawValue, cursorIndex) {
    if (typeof rawValue !== 'string') {
        throw new Error('parseDialogSuggestionContext requires rawValue string');
    }
    if (!Number.isInteger(cursorIndex)) {
        throw new Error('parseDialogSuggestionContext requires cursorIndex integer');
    }
    if (cursorIndex < 0 || cursorIndex > rawValue.length) {
        throw new Error('parseDialogSuggestionContext cursorIndex out of bounds');
    }

    let quoteChar = null;
    let inRegex = false;
    let prevSeparator = true;
    let index = 0;
    while (index < cursorIndex) {
        const ch = rawValue[index];

        if (quoteChar !== null) {
            if (ch === '\\' && index + 1 < cursorIndex) {
                index += 2;
                continue;
            }
            if (ch === quoteChar) {
                quoteChar = null;
            }
            index += 1;
            prevSeparator = false;
            continue;
        }

        if (inRegex) {
            if (ch === '\\' && index + 1 < cursorIndex) {
                index += 2;
                continue;
            }
            if (ch === '/') {
                inRegex = false;
            }
            index += 1;
            prevSeparator = false;
            continue;
        }

        if (ch === '"' || ch === "'") {
            quoteChar = ch;
            index += 1;
            prevSeparator = false;
            continue;
        }
        if (ch === '/' && prevSeparator) {
            inRegex = true;
            index += 1;
            prevSeparator = false;
            continue;
        }
        if (isSuggestionSeparator(ch)) {
            prevSeparator = true;
            index += 1;
            continue;
        }

        prevSeparator = false;
        index += 1;
    }

    if (quoteChar !== null || inRegex) {
        return null;
    }

    let start = cursorIndex;
    while (start > 0) {
        const ch = rawValue[start - 1];
        if (isSuggestionSeparator(ch)) {
            break;
        }
        start -= 1;
    }

    const token = rawValue.slice(start, cursorIndex);
    if (token === '') {
        return {
            partialPrefix: '',
            replaceStart: cursorIndex,
            replaceEnd: cursorIndex,
        };
    }
    if (!isValidTagPrefix(token)) {
        return null;
    }
    return {
        partialPrefix: token,
        replaceStart: start,
        replaceEnd: cursorIndex,
    };
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
        this._searchSelectedIndex = -1;
        this._dialogState = null;
        this._dialogAbortController = null;
        this._dialogSuggestionTimer = null;
        this._dialogRequestSerial = 0;
        this._dialogSelectedIndex = -1;
        this._dialogSuggestionContext = null;

        this._handleSearchInput = this._handleSearchInput.bind(this);
        this._handleSearchKeydown = this._handleSearchKeydown.bind(this);
        this._handleClick = this._handleClick.bind(this);
        this._handleMouseDownOutside = this._handleMouseDownOutside.bind(this);
        this._handleDialogInput = this._handleDialogInput.bind(this);
        this._handleDialogKeydown = this._handleDialogKeydown.bind(this);
        this._handleDialogOverlayClick = this._handleDialogOverlayClick.bind(this);
        this._handleDialogOverlayKeydown = this._handleDialogOverlayKeydown.bind(this);
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
        document.documentElement.classList.add('ontology-modal-open');
        document.body.classList.add('ontology-modal-open');
        this.renderSkeleton();
        void this.refreshTagSearch('');
    }

    onClose() {
        document.documentElement.classList.remove('ontology-modal-open');
        document.body.classList.remove('ontology-modal-open');
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }

        this._closeDialog(null);
        this._rulesCache = null;
        this._searchSelectedIndex = -1;
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

                <div class="ontology-busy" id="ontology-busy">
                    <div class="ontology-spinner"></div>
                    <div>Updating search index…</div>
                </div>

                <div class="ontology-search">
                    <div class="ontology-search-row">
                        <input
                            type="text"
                            id="ontology-search-input"
                            placeholder="Search tags…"
                            autocomplete="off"
                        />
                        <button class="ontology-add ontology-add-inline" data-action="add-tag">+ Add new tag…</button>
                    </div>
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

                <div class="ontology-dialog-overlay" id="ontology-dialog-overlay">
                    <div class="ontology-dialog" role="dialog" aria-modal="true" aria-labelledby="ontology-dialog-title">
                        <div class="ontology-dialog-header">
                            <h3 id="ontology-dialog-title"></h3>
                            <button class="ontology-dialog-close" data-action="dialog-cancel" aria-label="Close">×</button>
                        </div>
                        <div class="ontology-dialog-body">
                            <div class="ontology-dialog-description" id="ontology-dialog-description"></div>
                            <label class="ontology-dialog-label" id="ontology-dialog-label" for="ontology-dialog-input"></label>
                            <input
                                type="text"
                                id="ontology-dialog-input"
                                autocomplete="off"
                            />
                            <div class="ontology-dialog-help" id="ontology-dialog-help"></div>
                            <div class="ontology-dialog-suggestions" id="ontology-dialog-suggestions"></div>
                            <div class="ontology-dialog-error" id="ontology-dialog-error" style="display:none"></div>
                        </div>
                        <div class="ontology-dialog-footer">
                            <button class="ontology-dialog-secondary" data-action="dialog-cancel">Cancel</button>
                            <button class="ontology-dialog-primary" data-action="dialog-submit">Save</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        modalElement.style.display = 'block';
        modalElement.addEventListener('click', this._handleClick);
        modalElement.addEventListener('mousedown', this._handleMouseDownOutside);

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
            modalElement.removeEventListener('mousedown', this._handleMouseDownOutside);
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

    setBusy(isBusy) {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            return;
        }
        const target = modalElement.querySelector('#ontology-busy');
        if (!target) {
            return;
        }

        if (isBusy) {
            target.classList.add('is-visible');
        } else {
            target.classList.remove('is-visible');
        }
    }

    runBlockingCommand(name, asyncFn) {
        if (typeof name !== 'string' || name.trim() === '') {
            throw new Error('runBlockingCommand requires name');
        }
        if (typeof asyncFn !== 'function') {
            throw new Error('runBlockingCommand requires async function');
        }

        this.setBusy(true);
        return CommandGate.run(name, asyncFn).finally(() => {
            this.setBusy(false);
        });
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

    shouldCloseOnClickOutside() {
        return false;
    }

    _handleMouseDownOutside(event) {
        const modalElement = event.currentTarget;
        if (!(modalElement instanceof HTMLElement)) {
            return;
        }
        const modalContent = modalElement.querySelector('.modal-content');
        if (modalContent && !modalContent.contains(event.target)) {
            this.close();
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
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            return;
        }
        const container = modalElement.querySelector('#ontology-search-results');
        const hasContainer = container instanceof HTMLElement;
        let items = [];
        if (hasContainer) {
            items = Array.from(container.querySelectorAll('.ontology-search-result'));
        }
        const hasSuggestions = hasContainer && container.style.display !== 'none' && items.length > 0;

        if (event.key === 'ArrowDown' && hasSuggestions) {
            event.preventDefault();
            let currentIndex = this._searchSelectedIndex;
            if (!Number.isInteger(currentIndex)) {
                currentIndex = -1;
            }
            let nextIndex = currentIndex + 1;
            if (nextIndex < 0) {
                nextIndex = 0;
            }
            if (nextIndex > items.length - 1) {
                nextIndex = items.length - 1;
            }
            this._searchSelectedIndex = nextIndex;
            this._updateSearchSelection(container);
            return;
        }

        if (event.key === 'ArrowUp' && hasSuggestions) {
            event.preventDefault();
            let currentIndex = this._searchSelectedIndex;
            if (!Number.isInteger(currentIndex)) {
                currentIndex = 0;
            }
            let nextIndex = currentIndex - 1;
            if (nextIndex < 0) {
                nextIndex = 0;
            }
            this._searchSelectedIndex = nextIndex;
            this._updateSearchSelection(container);
            return;
        }

        if (event.key !== 'Enter') {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        if (typeof event.stopImmediatePropagation === 'function') {
            event.stopImmediatePropagation();
        }
        if (hasSuggestions) {
            let selectedIndex = this._searchSelectedIndex;
            if (!Number.isInteger(selectedIndex) || selectedIndex < 0 || selectedIndex >= items.length) {
                selectedIndex = 0;
            }
            const button = items[selectedIndex];
            if (!button) {
                return;
            }
            const tag = button.dataset.tag;
            if (typeof tag !== 'string' || tag.trim() === '') {
                throw new Error('ontology search suggestion missing tag');
            }
            this._applySearchSelection(tag);
            void this.setFocusTag(tag);
            return;
        }
        const state = this.getModalState();
        const query = state.searchQuery;
        if (typeof query !== 'string') {
            throw new Error('Modal searchQuery must be a string');
        }
        const trimmed = query.trim();
        if (trimmed === '') {
            return;
        }
        this._applySearchSelection(trimmed);
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
        if (!Array.isArray(tags) || tags.length === 0) {
            container.innerHTML = '';
            container.style.display = 'none';
            this._searchSelectedIndex = -1;
            return;
        }

        const rows = tags.map((entry) => {
            if (typeof entry === 'string') {
                return { tag: entry, count: null };
            }
            if (!entry || typeof entry !== 'object') {
                throw new Error('Ontology tag entry must be string or object');
            }
            const tag = entry.tag;
            const count = entry.count;
            if (typeof tag !== 'string' || tag.trim() === '') {
                throw new Error('Ontology tag entry missing tag');
            }
            if (!Number.isInteger(count) || count < 0) {
                throw new Error('Ontology tag entry missing count');
            }
            return { tag, count };
        });

        container.innerHTML = rows
            .map((row) => {
                const countBadge = row.count === null ? '' : `<span class="ontology-search-count">${row.count}</span>`;
                return (
                    `<button class="ontology-search-result" data-action="focus" data-tag="${escapeHtml(row.tag)}">` +
                    `<span class="ontology-search-label">${escapeHtml(row.tag)}</span>` +
                    `${countBadge}` +
                    `</button>`
                );
            })
            .join('');
        container.style.display = 'flex';
        this._searchSelectedIndex = 0;
        this._updateSearchSelection(container);
    }

    _getDialogElements() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            throw new Error('ontology modal element missing');
        }
        const overlay = modalElement.querySelector('#ontology-dialog-overlay');
        if (!(overlay instanceof HTMLElement)) {
            throw new Error('ontology dialog overlay missing');
        }
        const dialog = overlay.querySelector('.ontology-dialog');
        if (!(dialog instanceof HTMLElement)) {
            throw new Error('ontology dialog panel missing');
        }
        const title = overlay.querySelector('#ontology-dialog-title');
        if (!(title instanceof HTMLElement)) {
            throw new Error('ontology dialog title missing');
        }
        const description = overlay.querySelector('#ontology-dialog-description');
        if (!(description instanceof HTMLElement)) {
            throw new Error('ontology dialog description missing');
        }
        const label = overlay.querySelector('#ontology-dialog-label');
        if (!(label instanceof HTMLElement)) {
            throw new Error('ontology dialog label missing');
        }
        const input = overlay.querySelector('#ontology-dialog-input');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('ontology dialog input missing');
        }
        const help = overlay.querySelector('#ontology-dialog-help');
        if (!(help instanceof HTMLElement)) {
            throw new Error('ontology dialog help missing');
        }
        const suggestions = overlay.querySelector('#ontology-dialog-suggestions');
        if (!(suggestions instanceof HTMLElement)) {
            throw new Error('ontology dialog suggestions missing');
        }
        const error = overlay.querySelector('#ontology-dialog-error');
        if (!(error instanceof HTMLElement)) {
            throw new Error('ontology dialog error missing');
        }
        const submitButton = overlay.querySelector('.ontology-dialog-primary');
        if (!(submitButton instanceof HTMLElement)) {
            throw new Error('ontology dialog submit button missing');
        }
        return {
            overlay,
            dialog,
            title,
            description,
            label,
            input,
            help,
            suggestions,
            error,
            submitButton,
        };
    }

    _openDialog(config) {
        if (!config || typeof config !== 'object') {
            throw new Error('openDialog requires config object');
        }
        if (this._dialogState !== null) {
            throw new Error('Ontology dialog already open');
        }

        const title = config.title;
        if (typeof title !== 'string' || title.trim() === '') {
            throw new Error('Dialog title must be non-empty string');
        }
        const description = config.description;
        if (typeof description !== 'string') {
            throw new Error('Dialog description must be string');
        }
        const label = config.label;
        if (typeof label !== 'string' || label.trim() === '') {
            throw new Error('Dialog label must be non-empty string');
        }
        const placeholder = config.placeholder;
        if (typeof placeholder !== 'string') {
            throw new Error('Dialog placeholder must be string');
        }
        const submitLabel = config.submitLabel;
        if (typeof submitLabel !== 'string' || submitLabel.trim() === '') {
            throw new Error('Dialog submitLabel must be non-empty string');
        }
        const initialValue = config.initialValue;
        if (typeof initialValue !== 'string') {
            throw new Error('Dialog initialValue must be string');
        }
        const mode = config.mode;
        if (mode !== 'single-tag' && mode !== 'incoming' && mode !== 'rule') {
            throw new Error(`Unknown dialog mode: ${mode}`);
        }
        const helpText = config.helpText;
        if (!Array.isArray(helpText)) {
            throw new Error('Dialog helpText must be array');
        }
        for (const line of helpText) {
            if (typeof line !== 'string') {
                throw new Error('Dialog helpText entries must be strings');
            }
        }
        const suggestOnEmpty = config.suggestOnEmpty;
        if (typeof suggestOnEmpty !== 'boolean') {
            throw new Error('Dialog suggestOnEmpty must be boolean');
        }
        const autoSubmitOnSuggestion = config.autoSubmitOnSuggestion;
        if (typeof autoSubmitOnSuggestion !== 'boolean') {
            throw new Error('Dialog autoSubmitOnSuggestion must be boolean');
        }

        const focusTag = config.focusTag;
        if (mode === 'incoming') {
            if (typeof focusTag !== 'string' || focusTag.trim() === '') {
                throw new Error('Dialog focusTag must be non-empty string for incoming rules');
            }
        } else {
            if (focusTag !== null) {
                throw new Error('Dialog focusTag must be null for non-incoming rules');
            }
        }

        return new Promise((resolve) => {
            this._dialogState = {
                title,
                description,
                label,
                placeholder,
                submitLabel,
                initialValue,
                mode,
                helpText,
                focusTag,
                resolve,
                suggestOnEmpty,
                autoSubmitOnSuggestion,
            };
            this._renderDialog();
        });
    }

    _renderDialog() {
        const state = this._dialogState;
        if (!state) {
            throw new Error('Dialog state missing');
        }

        const elements = this._getDialogElements();
        elements.overlay.classList.add('is-visible');
        elements.overlay.setAttribute('aria-hidden', 'false');

        elements.title.textContent = state.title;
        if (state.description.trim() === '') {
            elements.description.textContent = '';
            elements.description.style.display = 'none';
        } else {
            elements.description.textContent = state.description;
            elements.description.style.display = 'block';
        }

        elements.label.textContent = state.label;
        elements.input.placeholder = state.placeholder;
        elements.input.value = state.initialValue;
        elements.submitButton.textContent = state.submitLabel;

        if (state.helpText.length === 0) {
            elements.help.innerHTML = '';
            elements.help.style.display = 'none';
        } else {
            elements.help.innerHTML = state.helpText
                .map((line) => `<div>${escapeHtml(line)}</div>`)
                .join('');
            elements.help.style.display = 'block';
        }

        this._clearDialogError();
        this._hideDialogSuggestions();
        this._attachDialogListeners(elements);

        setTimeout(() => {
            elements.input.focus();
            const length = elements.input.value.length;
            if (typeof elements.input.setSelectionRange === 'function') {
                elements.input.setSelectionRange(length, length);
            }
            this._updateDialogSuggestions();
        }, 30);
    }

    _attachDialogListeners(elements) {
        if (!elements || typeof elements !== 'object') {
            throw new Error('attachDialogListeners requires elements');
        }
        this._detachDialogListeners();
        elements.input.addEventListener('input', this._handleDialogInput);
        elements.input.addEventListener('keydown', this._handleDialogKeydown);
        elements.overlay.addEventListener('mousedown', this._handleDialogOverlayClick);
        elements.overlay.addEventListener('keydown', this._handleDialogOverlayKeydown);
    }

    _detachDialogListeners() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            return;
        }
        const overlay = modalElement.querySelector('#ontology-dialog-overlay');
        if (!(overlay instanceof HTMLElement)) {
            return;
        }
        const input = overlay.querySelector('#ontology-dialog-input');
        if (input instanceof HTMLInputElement) {
            input.removeEventListener('input', this._handleDialogInput);
            input.removeEventListener('keydown', this._handleDialogKeydown);
        }
        overlay.removeEventListener('mousedown', this._handleDialogOverlayClick);
        overlay.removeEventListener('keydown', this._handleDialogOverlayKeydown);
    }

    _hideDialogOverlay() {
        const elements = this._getDialogElements();
        elements.overlay.classList.remove('is-visible');
        elements.overlay.setAttribute('aria-hidden', 'true');
    }

    _closeDialog(result) {
        const state = this._dialogState;
        if (!state) {
            return;
        }
        this._dialogState = null;
        this._hideDialogSuggestions();
        this._resetDialogSuggestionState();
        this._clearDialogError();
        this._detachDialogListeners();
        this._hideDialogOverlay();

        const resolve = state.resolve;
        if (typeof resolve !== 'function') {
            throw new Error('Dialog resolve missing');
        }
        resolve(result);
    }

    _setDialogError(message) {
        if (typeof message !== 'string' || message.trim() === '') {
            throw new Error('setDialogError requires non-empty string');
        }
        const elements = this._getDialogElements();
        elements.error.textContent = message;
        elements.error.style.display = 'block';
    }

    _clearDialogError() {
        const elements = this._getDialogElements();
        elements.error.textContent = '';
        elements.error.style.display = 'none';
    }

    _resetDialogSuggestionState() {
        if (this._dialogSuggestionTimer) {
            clearTimeout(this._dialogSuggestionTimer);
            this._dialogSuggestionTimer = null;
        }
        if (this._dialogAbortController) {
            this._dialogAbortController.abort();
            this._dialogAbortController = null;
        }
        this._dialogRequestSerial += 1;
        this._dialogSelectedIndex = -1;
        this._dialogSuggestionContext = null;
    }

    _hideDialogSuggestions() {
        const elements = this._getDialogElements();
        elements.suggestions.innerHTML = '';
        elements.suggestions.style.display = 'none';
        this._dialogSelectedIndex = -1;
        this._dialogSuggestionContext = null;
    }

    _renderDialogSuggestions(tags) {
        const elements = this._getDialogElements();
        if (!Array.isArray(tags) || tags.length === 0) {
            this._hideDialogSuggestions();
            return;
        }

        const rows = tags.map((entry) => {
            if (typeof entry === 'string') {
                return { tag: entry, count: null };
            }
            if (!entry || typeof entry !== 'object') {
                throw new Error('Ontology dialog suggestion entry must be string or object');
            }
            const tag = entry.tag;
            const count = entry.count;
            if (typeof tag !== 'string' || tag.trim() === '') {
                throw new Error('Ontology dialog suggestion missing tag');
            }
            if (!Number.isInteger(count) || count < 0) {
                throw new Error('Ontology dialog suggestion missing count');
            }
            return { tag, count };
        });

        elements.suggestions.innerHTML = rows
            .map((row) => {
                const countBadge = row.count === null ? '' : `<span class="ontology-dialog-suggestion-count">${row.count}</span>`;
                return (
                    `<button type="button" class="ontology-dialog-suggestion" data-tag="${escapeHtml(row.tag)}">` +
                    `<span class="ontology-dialog-suggestion-label">${escapeHtml(row.tag)}</span>` +
                    `${countBadge}` +
                    `</button>`
                );
            })
            .join('');
        elements.suggestions.style.display = 'flex';
        this._dialogSelectedIndex = 0;
        this._updateDialogSuggestionSelection(elements.suggestions);

        elements.suggestions.querySelectorAll('.ontology-dialog-suggestion').forEach((button) => {
            button.addEventListener('mousedown', (event) => {
                event.preventDefault();
                const tag = button.dataset.tag;
                if (typeof tag !== 'string' || tag.trim() === '') {
                    throw new Error('Ontology dialog suggestion missing tag');
                }
                this._applyDialogSuggestion(tag);
                const state = this._dialogState;
                if (state && state.autoSubmitOnSuggestion) {
                    this._submitDialog();
                }
            });
        });
    }

    _updateDialogSuggestionSelection(container) {
        if (!(container instanceof HTMLElement)) {
            throw new Error('dialog suggestion container missing');
        }
        const items = Array.from(container.querySelectorAll('.ontology-dialog-suggestion'));
        if (items.length === 0) {
            this._dialogSelectedIndex = -1;
            return;
        }
        if (!Number.isInteger(this._dialogSelectedIndex)) {
            this._dialogSelectedIndex = 0;
        }
        if (this._dialogSelectedIndex < 0 || this._dialogSelectedIndex >= items.length) {
            this._dialogSelectedIndex = 0;
        }
        items.forEach((item, index) => {
            item.classList.toggle('is-selected', index === this._dialogSelectedIndex);
        });
        const selected = items[this._dialogSelectedIndex];
        if (selected && typeof selected.scrollIntoView === 'function') {
            selected.scrollIntoView({ block: 'nearest' });
        }
    }

    _applyDialogSuggestion(tag) {
        if (typeof tag !== 'string' || tag.trim() === '') {
            throw new Error('applyDialogSuggestion requires non-empty tag');
        }
        const state = this._dialogState;
        if (!state) {
            throw new Error('Dialog state missing');
        }
        const elements = this._getDialogElements();
        const input = elements.input;

        if (state.mode === 'single-tag') {
            input.value = tag;
            const length = tag.length;
            if (typeof input.setSelectionRange === 'function') {
                input.setSelectionRange(length, length);
            }
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.focus();
            this._hideDialogSuggestions();
            return;
        }

        const context = this._dialogSuggestionContext;
        if (!context || typeof context.replaceStart !== 'number' || typeof context.replaceEnd !== 'number') {
            throw new Error('Dialog suggestion context missing');
        }
        const rawValue = input.value;
        if (typeof rawValue !== 'string') {
            throw new Error('Dialog input value missing');
        }

        const before = rawValue.slice(0, context.replaceStart);
        const after = rawValue.slice(context.replaceEnd);
        const nextValue = `${before}${tag}${after}`;
        input.value = nextValue;
        const nextCursor = before.length + tag.length;
        if (typeof input.setSelectionRange === 'function') {
            input.setSelectionRange(nextCursor, nextCursor);
        }
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.focus();
        this._hideDialogSuggestions();
    }

    _handleDialogInput(event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
            throw new Error('Expected dialog input element');
        }
        this._clearDialogError();
        this._updateDialogSuggestions();
    }

    _handleDialogKeydown(event) {
        const state = this._dialogState;
        if (!state) {
            return;
        }
        const elements = this._getDialogElements();
        const container = elements.suggestions;
        const items = Array.from(container.querySelectorAll('.ontology-dialog-suggestion'));
        const hasSuggestions = container.style.display !== 'none' && items.length > 0;

        if (event.key === 'ArrowDown' && hasSuggestions) {
            event.preventDefault();
            event.stopPropagation();
            this._dialogSelectedIndex = Math.min(this._dialogSelectedIndex + 1, items.length - 1);
            this._updateDialogSuggestionSelection(container);
            return;
        }

        if (event.key === 'ArrowUp' && hasSuggestions) {
            event.preventDefault();
            event.stopPropagation();
            this._dialogSelectedIndex = Math.max(this._dialogSelectedIndex - 1, 0);
            this._updateDialogSuggestionSelection(container);
            return;
        }

        if (event.key === 'Enter') {
            event.preventDefault();
            event.stopPropagation();
            if (typeof event.stopImmediatePropagation === 'function') {
                event.stopImmediatePropagation();
            }
            if (hasSuggestions) {
                let selectedIndex = this._dialogSelectedIndex;
                if (!Number.isInteger(selectedIndex) || selectedIndex < 0 || selectedIndex >= items.length) {
                    selectedIndex = 0;
                }
                const button = items[selectedIndex];
                if (!button) {
                    return;
                }
                const tag = button.dataset.tag;
                if (typeof tag !== 'string' || tag.trim() === '') {
                    throw new Error('Dialog suggestion missing tag');
                }
                this._applyDialogSuggestion(tag);
                if (state.autoSubmitOnSuggestion) {
                    this._submitDialog();
                }
                return;
            }
            this._submitDialog();
            return;
        }

        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            if (typeof event.stopImmediatePropagation === 'function') {
                event.stopImmediatePropagation();
            }
            this._closeDialog(null);
        }
    }

    _handleDialogOverlayClick(event) {
        const overlay = event.currentTarget;
        if (!(overlay instanceof HTMLElement)) {
            return;
        }
        const dialog = overlay.querySelector('.ontology-dialog');
        if (dialog && !dialog.contains(event.target)) {
            event.preventDefault();
            this._closeDialog(null);
        }
    }

    _handleDialogOverlayKeydown(event) {
        if (event.key !== 'Escape') {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        if (typeof event.stopImmediatePropagation === 'function') {
            event.stopImmediatePropagation();
        }
        this._closeDialog(null);
    }

    _updateDialogSuggestions() {
        const state = this._dialogState;
        if (!state) {
            return;
        }
        const elements = this._getDialogElements();
        const input = elements.input;
        const rawValue = input.value;
        if (typeof rawValue !== 'string') {
            throw new Error('Dialog input value missing');
        }

        let query = null;
        let context = null;

        if (state.mode === 'single-tag') {
            const trimmed = rawValue.trim();
            if (/\s/.test(trimmed)) {
                this._hideDialogSuggestions();
                return;
            }
            query = trimmed;
        } else {
            if (!Number.isInteger(input.selectionStart)) {
                throw new Error('Dialog input selectionStart missing');
            }
            context = parseDialogSuggestionContext(rawValue, input.selectionStart);
            if (context === null) {
                this._hideDialogSuggestions();
                return;
            }
            query = context.partialPrefix;
        }

        if (query === null) {
            this._hideDialogSuggestions();
            return;
        }
        if (query === '' && !state.suggestOnEmpty) {
            this._hideDialogSuggestions();
            return;
        }

        if (this._dialogSuggestionTimer) {
            clearTimeout(this._dialogSuggestionTimer);
            this._dialogSuggestionTimer = null;
        }

        const requestId = ++this._dialogRequestSerial;
        this._dialogSuggestionTimer = setTimeout(() => {
            this._dialogSuggestionTimer = null;
            this._fetchDialogSuggestions(query).then((tags) => {
                if (requestId !== this._dialogRequestSerial) {
                    return;
                }
                if (!this._dialogState) {
                    return;
                }
                if (tags === null) {
                    return;
                }
                this._dialogSuggestionContext = context;
                this._renderDialogSuggestions(tags);
            }).catch((error) => {
                if (requestId !== this._dialogRequestSerial) {
                    return;
                }
                if (!this._dialogState) {
                    return;
                }
                const message = error instanceof Error ? error.message : String(error);
                this._setDialogError(message);
                this._hideDialogSuggestions();
            });
        }, DIALOG_SUGGESTION_DEBOUNCE_MS);
    }

    async _fetchDialogSuggestions(query) {
        if (typeof query !== 'string') {
            throw new Error('fetchDialogSuggestions requires query string');
        }
        if (this._dialogAbortController) {
            this._dialogAbortController.abort();
        }
        const controller = new AbortController();
        this._dialogAbortController = controller;

        const url = `${ONTOLOGY_BASE}/tags?q=${encodeURIComponent(query)}&limit=${DIALOG_SUGGESTION_LIMIT}`;
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
            return null;
        }
        if (!response.ok) {
            const payload = await response.json().catch(() => null);
            if (payload && typeof payload.detail === 'string') {
                throw new Error(payload.detail);
            }
            throw new Error(`Request failed: ${response.status} ${response.statusText}`);
        }

        const payload = await response.json();
        if (this._dialogAbortController !== controller) {
            return null;
        }

        const tags = payload.tags;
        const totalCount = payload.totalCount;
        if (!Array.isArray(tags)) {
            throw new Error('Ontology tags payload missing tags array');
        }
        if (!Number.isInteger(totalCount) || totalCount < 0) {
            throw new Error('Ontology tags payload missing totalCount');
        }
        return tags;
    }

    _submitDialog() {
        const state = this._dialogState;
        if (!state) {
            return;
        }
        const elements = this._getDialogElements();
        const input = elements.input;
        const rawValue = input.value;
        if (typeof rawValue !== 'string') {
            throw new Error('Dialog input value missing');
        }

        this._clearDialogError();
        const trimmed = rawValue.trim();

        if (state.mode === 'single-tag') {
            if (trimmed === '') {
                this._setDialogError('Enter a tag.');
                return;
            }
            if (!isValidTagToken(trimmed)) {
                this._setDialogError(
                    'That input is not a valid tag token. ' +
                    'This action only supports a single tag (no spaces, quotes, regex, or parentheses).'
                );
                return;
            }
            this._closeDialog(trimmed);
            return;
        }

        if (state.mode === 'incoming') {
            if (trimmed === '') {
                this._setDialogError('Enter at least one condition.');
                return;
            }
            let atoms;
            try {
                atoms = parseIncomingAtoms(trimmed);
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                this._setDialogError(message);
                return;
            }
            if (!Array.isArray(atoms) || atoms.length === 0) {
                this._setDialogError('Enter at least one condition.');
                return;
            }
            const rhsTag = state.focusTag;
            if (typeof rhsTag !== 'string' || rhsTag.trim() === '') {
                throw new Error('Dialog focusTag missing');
            }
            let ruleText = null;
            if (atoms.length === 1) {
                ruleText = `${atoms[0]} => ${rhsTag}`;
            } else {
                ruleText = `(${atoms.join(' ')}) => ${rhsTag}`;
            }
            this._closeDialog(ruleText);
            return;
        }

        if (state.mode === 'rule') {
            if (trimmed === '') {
                this._setDialogError('Enter a rule.');
                return;
            }
            this._closeDialog(trimmed);
            return;
        }

        throw new Error(`Unknown dialog mode: ${state.mode}`);
    }

    _updateSearchSelection(container) {
        if (!(container instanceof HTMLElement)) {
            throw new Error('ontology search results container missing');
        }
        const items = Array.from(container.querySelectorAll('.ontology-search-result'));
        if (items.length === 0) {
            this._searchSelectedIndex = -1;
            return;
        }
        if (!Number.isInteger(this._searchSelectedIndex)) {
            this._searchSelectedIndex = 0;
        }
        if (this._searchSelectedIndex < 0 || this._searchSelectedIndex >= items.length) {
            this._searchSelectedIndex = 0;
        }
        items.forEach((item, index) => {
            item.classList.toggle('is-selected', index === this._searchSelectedIndex);
        });
        const selected = items[this._searchSelectedIndex];
        if (selected && typeof selected.scrollIntoView === 'function') {
            selected.scrollIntoView({ block: 'nearest' });
        }
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
            const sortKey = (() => {
                if (Array.isArray(lhsAtoms) && lhsAtoms.length > 0) {
                    const atom = lhsAtoms[0];
                    if (atom && typeof atom === 'object') {
                        if (atom.kind === 'tag' && typeof atom.tag === 'string') {
                            return atom.tag;
                        }
                        if (atom.kind === 'text' && typeof atom.text === 'string') {
                            return atom.text;
                        }
                        if (atom.kind === 'regex' && typeof atom.regex === 'string') {
                            return atom.regex;
                        }
                    }
                }
                if (typeof display === 'string') {
                    return display;
                }
                return '';
            })();

            return {
                ruleId,
                lhs,
                sortKey,
            };
        }).sort((a, b) => {
            const keyCompare = a.sortKey.localeCompare(b.sortKey, undefined, { sensitivity: 'base' });
            if (keyCompare !== 0) {
                return keyCompare;
            }
            return a.ruleId - b.ruleId;
        }).map((row) => {
            return `
                <div class="ontology-row">
                    <div class="ontology-rule-left">
                        ${row.lhs}
                    </div>
                    <div class="ontology-row-actions">
                        <button class="ontology-edit" data-action="edit-incoming" data-rule-id="${row.ruleId}" aria-label="Edit">✎</button>
                        <button class="ontology-remove" data-action="remove" data-rule-ids="${row.ruleId}" aria-label="Remove">−</button>
                    </div>
                </div>
            `;
        });

        const indirectHtml = indirectTags.map((tag) => {
            if (typeof tag !== 'string') {
                throw new Error('indirect tag must be string');
            }
            return tag;
        }).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' })).map((tag) => {
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
            return row;
        }).sort((a, b) => a.tag.localeCompare(b.tag, undefined, { sensitivity: 'base' })).map((row) => {
            const tag = row.tag;
            const ruleIds = row.ruleIds;
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
            return tag;
        }).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' })).map((tag) => {
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

        const payload = await this.runBlockingCommand('ontologyModal.createRule', async () => {
            return fetchJson(`${ONTOLOGY_BASE}/rules`, {
                method: 'POST',
                headers: buildAuthHeaders(),
                body: JSON.stringify({ text }),
            });
        });
        if (payload === null) {
            return;
        }

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

        const next = await this._openDialog({
            title: 'Edit rule',
            description: 'Update the full rule text.',
            label: 'Rule text',
            placeholder: 'tag => other-tag',
            submitLabel: 'Save rule',
            initialValue: existing,
            mode: 'rule',
            helpText: [
                'Use => for implications, = for synonyms.',
                'Quoted text and /regex/ are allowed on the left side only.',
            ],
            focusTag: null,
            suggestOnEmpty: true,
            autoSubmitOnSuggestion: false,
        });
        if (next === null) {
            return;
        }
        if (typeof next !== 'string' || next.trim() === '') {
            throw new Error('Dialog returned invalid rule text');
        }
        const normalizedExisting = existing.trim();
        if (next === normalizedExisting) {
            return;
        }

        const payload = await this.runBlockingCommand('ontologyModal.editRule', async () => {
            return fetchJson(`${ONTOLOGY_BASE}/rules/${ruleId}`, {
                method: 'PUT',
                headers: buildAuthHeaders(),
                body: JSON.stringify({ text: next }),
            });
        });
        if (payload === null) {
            return;
        }
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

        const updatedText = await this._openDialog({
            title: 'Edit incoming rule',
            description: `Condition that implies '${rhs}'.`,
            label: 'Condition',
            placeholder: 'tag "text" /regex/ another-tag',
            submitLabel: 'Save rule',
            initialValue: editValue,
            mode: 'incoming',
            helpText: [
                'Tags can be combined with spaces for AND.',
                'Quoted text and /regex/ are allowed.',
                'Tag suggestions appear only for tag tokens.',
            ],
            focusTag: rhs,
            suggestOnEmpty: true,
            autoSubmitOnSuggestion: false,
        });
        if (updatedText === null) {
            return;
        }
        if (typeof updatedText !== 'string' || updatedText.trim() === '') {
            throw new Error('Dialog returned invalid incoming rule text');
        }

        const payload = await this.runBlockingCommand('ontologyModal.editIncomingRule', async () => {
            return fetchJson(`${ONTOLOGY_BASE}/rules/${ruleId}`, {
                method: 'PUT',
                headers: buildAuthHeaders(),
                body: JSON.stringify({ text: updatedText }),
            });
        });
        if (payload === null) {
            return;
        }
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

        const next = await this._openDialog({
            title: 'Rename tag',
            description: 'Renames the tag everywhere (rules and note tag bars).',
            label: 'New tag',
            placeholder: 'new-tag-name',
            submitLabel: 'Rename',
            initialValue: focusTag,
            mode: 'single-tag',
            helpText: ['Single tag token only.'],
            focusTag: null,
            suggestOnEmpty: true,
            autoSubmitOnSuggestion: true,
        });
        if (next === null) {
            return;
        }
        if (typeof next !== 'string' || next.trim() === '') {
            throw new Error('Dialog returned invalid tag');
        }
        const trimmed = next.trim();
        if (trimmed === focusTag) {
            return;
        }

        const confirmed = window.confirm(
            `Rename tag '${focusTag}' → '${trimmed}' in ontology rules?\n\n` +
            'This renames the tag in BOTH ontology rules and all note tag bars.\n' +
            'This cannot be undone automatically.'
        );
        if (!confirmed) {
            return;
        }

        const payload = await this.runBlockingCommand('ontologyModal.renameTag', async () => {
            return fetchJson(`${ONTOLOGY_BASE}/rename-tag`, {
                method: 'POST',
                headers: buildAuthHeaders(),
                body: JSON.stringify({ old: focusTag, new: trimmed }),
            });
        });
        if (payload === null) {
            return;
        }
        this._rulesCache = null;
        await this.setFocusTag(trimmed);
    }

    async _deleteRuleRequest(ruleId) {
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

        const payload = await this.runBlockingCommand('ontologyModal.deleteRules', async () => {
            for (const ruleId of ruleIds) {
                await this._deleteRuleRequest(ruleId);
            }
            return { ok: true };
        });
        if (payload === null) {
            return;
        }
        this._rulesCache = null;
    }

    async _handleClick(event) {
        await (async () => {
            const rawTarget = event.target;
            if (!(rawTarget instanceof HTMLElement)) {
                return;
            }
            const target = rawTarget.closest('[data-action]');
            if (!(target instanceof HTMLElement)) {
                return;
            }
            const action = target.dataset.action;
            if (typeof action !== 'string') {
                return;
            }

            this.renderError(null);

            if (action === 'dialog-cancel') {
                this._closeDialog(null);
                return;
            }

            if (action === 'dialog-submit') {
                this._submitDialog();
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
                if (target.classList.contains('ontology-search-result')) {
                    this._applySearchSelection(tag);
                }
                void this.setFocusTag(tag);
                return;
            }

            if (action === 'rename-focus') {
                await this._renameFocusedTag();
                return;
            }

            if (action === 'add-tag') {
                const newTag = await this._openDialog({
                    title: 'Add new tag',
                    description: 'Create a tag to focus on in the relationships editor.',
                    label: 'Tag',
                    placeholder: 'python',
                    submitLabel: 'Add tag',
                    initialValue: '',
                    mode: 'single-tag',
                    helpText: ['Single tag token only.'],
                    focusTag: null,
                    suggestOnEmpty: true,
                    autoSubmitOnSuggestion: true,
                });
                if (newTag === null) {
                    return;
                }
                if (typeof newTag !== 'string' || newTag.trim() === '') {
                    throw new Error('Dialog returned invalid tag');
                }
                if (this._abortController) {
                    this._abortController.abort();
                    this._abortController = null;
                }
                const modalElement = document.getElementById(this.modalElementId);
                const input = modalElement ? modalElement.querySelector('#ontology-search-input') : null;
                if (input instanceof HTMLInputElement) {
                    input.value = '';
                }
                this.updateModalState({ searchQuery: '' });
                this.renderTagSearchResults([]);
                await this.setFocusTag(newTag);
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
                const ruleText = await this._openDialog({
                    title: `Add condition for '${focusTag}'`,
                    description: `Create a condition that implies '${focusTag}'.`,
                    label: 'Condition',
                    placeholder: 'tag "text" /regex/ another-tag',
                    submitLabel: 'Add rule',
                    initialValue: '',
                    mode: 'incoming',
                    helpText: [
                        'Combine tags with spaces for AND.',
                        'Quoted text and /regex/ are allowed.',
                        'Tag suggestions appear only for tag tokens.',
                    ],
                    focusTag: focusTag,
                    suggestOnEmpty: true,
                    autoSubmitOnSuggestion: false,
                });
                if (ruleText === null) {
                    return;
                }
                if (typeof ruleText !== 'string' || ruleText.trim() === '') {
                    throw new Error('Dialog returned invalid incoming rule');
                }
                await this._createRule(ruleText);
            } else if (action === 'add-right') {
                const newTag = await this._openDialog({
                    title: `Tag implied by '${focusTag}'`,
                    description: `Add a tag that '${focusTag}' implies.`,
                    label: 'Implied tag',
                    placeholder: 'related-tag',
                    submitLabel: 'Add implication',
                    initialValue: '',
                    mode: 'single-tag',
                    helpText: ['Single tag token only.'],
                    focusTag: null,
                    suggestOnEmpty: true,
                    autoSubmitOnSuggestion: true,
                });
                if (newTag === null) {
                    return;
                }
                if (typeof newTag !== 'string' || newTag.trim() === '') {
                    throw new Error('Dialog returned invalid tag');
                }
                await this._createRule(`${focusTag} => ${newTag}`);
            } else {
                const newTag = await this._openDialog({
                    title: `Synonym for '${focusTag}'`,
                    description: `Add a synonym for '${focusTag}'.`,
                    label: 'Synonym tag',
                    placeholder: 'alternate-tag',
                    submitLabel: 'Add synonym',
                    initialValue: '',
                    mode: 'single-tag',
                    helpText: ['Single tag token only.'],
                    focusTag: null,
                    suggestOnEmpty: true,
                    autoSubmitOnSuggestion: true,
                });
                if (newTag === null) {
                    return;
                }
                if (typeof newTag !== 'string' || newTag.trim() === '') {
                    throw new Error('Dialog returned invalid tag');
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

    _applySearchSelection(tag) {
        if (typeof tag !== 'string' || tag.trim() === '') {
            throw new Error('applySearchSelection requires non-empty tag');
        }
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            return;
        }
        const input = modalElement.querySelector('#ontology-search-input');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('ontology search input missing');
        }
        input.value = tag;
        this.updateModalState({ searchQuery: tag });
        input.blur();
    }
}
