import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';
import { actionRefreshAndMaybeSelect } from '../mode-manager/actions/ui-actions.js';
import { actionSaveAndExitEditingWithoutRefreshing } from '../mode-manager/actions/selection-actions.js';
import { NotesAPI } from '../api-client.js';
import { PasswordModal } from '../modals/password-modal.js';
import { syncSearchInputValue } from '../mode-manager/services/search-input-service.js';

import { buildCommandPaletteEndpoints } from './endpoint-registry.js';
import { PreferencesStore } from './preferences-store.js';
import { loadCommandPaletteTagMap } from './tag-config-loader.js';
import { UsageStore } from './usage-store.js';

function trimToken(token) {
    if (typeof token !== 'string') {
        throw new Error('trimToken requires string');
    }
    return token.replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, '');
}

function tokenizeQuery(rawQuery) {
    if (typeof rawQuery !== 'string') {
        throw new Error('tokenizeQuery requires rawQuery string');
    }

    const lower = rawQuery.toLowerCase();
    const endsWithSpace = lower.length > 0 && /\s$/.test(lower);
    const rawTokens = lower.split(/\s+/).filter((t) => t.length > 0);
    const cleanedTokens = rawTokens.map(trimToken).filter((t) => t.length > 0);

    if (cleanedTokens.length === 0) {
        return { committed: [], prefix: null };
    }

    if (endsWithSpace) {
        return { committed: cleanedTokens, prefix: null };
    }

    if (cleanedTokens.length === 1) {
        return { committed: [], prefix: cleanedTokens[0] };
    }

    return {
        committed: cleanedTokens.slice(0, cleanedTokens.length - 1),
        prefix: cleanedTokens[cleanedTokens.length - 1],
    };
}

function endpointMatchesTags(endpoint, committedTokens) {
    if (!endpoint || typeof endpoint !== 'object') {
        throw new Error('endpointMatchesTags requires endpoint');
    }
    if (!Array.isArray(committedTokens)) {
        throw new Error('endpointMatchesTags requires committedTokens array');
    }
    if (!(endpoint.tags instanceof Set)) {
        throw new Error('Endpoint missing tags Set');
    }

    for (const token of committedTokens) {
        if (typeof token !== 'string') {
            throw new Error('Committed tokens must be strings');
        }
        if (!endpoint.tags.has(token)) {
            return false;
        }
    }
    return true;
}

function endpointMatchesPrefix(endpoint, prefix) {
    if (!endpoint || typeof endpoint !== 'object') {
        throw new Error('endpointMatchesPrefix requires endpoint');
    }
    if (typeof prefix !== 'string' || prefix.length === 0) {
        throw new Error('endpointMatchesPrefix requires prefix string');
    }
    if (!(endpoint.tags instanceof Set)) {
        throw new Error('Endpoint missing tags Set');
    }

    for (const tag of endpoint.tags) {
        if (tag.startsWith(prefix)) {
            return true;
        }
    }
    return false;
}

function sortMatchesByUsage(matches, usageSnapshot) {
    if (!Array.isArray(matches)) {
        throw new Error('sortMatchesByUsage requires matches array');
    }
    if (!usageSnapshot || typeof usageSnapshot !== 'object') {
        throw new Error('sortMatchesByUsage requires usageSnapshot');
    }

    return matches.slice().sort((a, b) => {
        const au = Object.prototype.hasOwnProperty.call(usageSnapshot, a.id) ? usageSnapshot[a.id] : null;
        const bu = Object.prototype.hasOwnProperty.call(usageSnapshot, b.id) ? usageSnapshot[b.id] : null;

        const aCount = au && typeof au.count === 'number' ? au.count : 0;
        const bCount = bu && typeof bu.count === 'number' ? bu.count : 0;
        if (aCount !== bCount) {
            return bCount - aCount;
        }

        const aLast = au && typeof au.lastUsedAt === 'number' ? au.lastUsedAt : 0;
        const bLast = bu && typeof bu.lastUsedAt === 'number' ? bu.lastUsedAt : 0;
        if (aLast !== bLast) {
            return bLast - aLast;
        }

        return a.label.localeCompare(b.label);
    });
}

function computeSuggestedTags(matches, committedTokens, prefix, usageSnapshot) {
    if (!Array.isArray(matches)) {
        throw new Error('computeSuggestedTags requires matches array');
    }
    if (!Array.isArray(committedTokens)) {
        throw new Error('computeSuggestedTags requires committedTokens array');
    }
    if (prefix !== null && typeof prefix !== 'string') {
        throw new Error('computeSuggestedTags prefix must be string or null');
    }
    if (!usageSnapshot || typeof usageSnapshot !== 'object') {
        throw new Error('computeSuggestedTags requires usageSnapshot');
    }

    const committedSet = new Set(committedTokens);
    const total = matches.length;
    const tagStats = new Map();

    for (const endpoint of matches) {
        for (const tag of endpoint.tags) {
            if (committedSet.has(tag)) {
                continue;
            }
            if (prefix && !tag.startsWith(prefix)) {
                continue;
            }
            if (!tagStats.has(tag)) {
                tagStats.set(tag, { endpointIds: new Set(), usage: 0 });
            }
            const stat = tagStats.get(tag);
            stat.endpointIds.add(endpoint.id);
        }
    }

    for (const [tag, stat] of tagStats.entries()) {
        let usage = 0;
        for (const endpointId of stat.endpointIds) {
            const record = Object.prototype.hasOwnProperty.call(usageSnapshot, endpointId)
                ? usageSnapshot[endpointId]
                : null;
            if (record && typeof record.count === 'number') {
                usage += record.count;
            }
        }
        stat.usage = usage;
    }

    const suggestions = [];
    for (const [tag, stat] of tagStats.entries()) {
        const matchCount = stat.endpointIds.size;
        const narrowingPower = total > 0 ? (total - matchCount) / total : 0;
        suggestions.push({ tag, matchCount, narrowingPower, usage: stat.usage });
    }

    suggestions.sort((a, b) => {
        if (a.narrowingPower !== b.narrowingPower) {
            return b.narrowingPower - a.narrowingPower;
        }
        if (a.usage !== b.usage) {
            return b.usage - a.usage;
        }
        return a.tag.localeCompare(b.tag);
    });

    return suggestions.slice(0, 10).map((s) => s.tag);
}

function ensureModalStack() {
    if (!ModeContext.modalStack) {
        ModeContext.modalStack = [];
    }
    if (!Array.isArray(ModeContext.modalStack)) {
        throw new Error('ModeContext.modalStack must be an array');
    }
    return ModeContext.modalStack;
}

class CommandPaletteController {
    constructor() {
        this._initialized = false;
        this._tagMap = null;
        this._allTags = new Set();
        this._endpoints = [];

        this._isOpen = false;
        this._previousActiveElement = null;
        this._previousScrollY = null;
        this._previousSelection = { query: '', selectedIndex: 0 };

        this._preferences = new PreferencesStore();
        this._usage = new UsageStore();

        this._elements = null;

        this._handleKeyDown = this._handleKeyDown.bind(this);
        this._handleInput = this._handleInput.bind(this);
        this._handleClick = this._handleClick.bind(this);
    }

    async init() {
        if (this._initialized) {
            return;
        }
        this._tagMap = await loadCommandPaletteTagMap();

        this._allTags.clear();
        for (const tags of this._tagMap.values()) {
            for (const tag of tags) {
                this._allTags.add(tag);
            }
        }

        this._endpoints = buildCommandPaletteEndpoints({
            preferencesStore: this._preferences,
            actions: {
                applyPreference: this.applyPreference.bind(this),
                openPasswordManager: this.openPasswordManager.bind(this),
                collapseAll: this.collapseAll.bind(this),
                expandAll: this.expandAll.bind(this),
                resetViewFilters: this.resetViewFilters.bind(this),
                resetAllPreferences: this.resetAllPreferences.bind(this),
            },
        });

        this._mergeAndValidateTags();
        this._ensureDom();

        this._applyPreferenceEffectsFromStorage();

        this._initialized = true;
    }

    _mergeAndValidateTags() {
        if (!(this._tagMap instanceof Map)) {
            throw new Error('Command palette tag map not loaded');
        }

        const endpointsById = new Map();
        for (const endpoint of this._endpoints) {
            if (!endpoint || typeof endpoint !== 'object') {
                throw new Error('Command palette endpoint registry contains invalid endpoint');
            }
            if (typeof endpoint.id !== 'string' || endpoint.id.length === 0) {
                throw new Error('Command palette endpoints must have id');
            }
            if (endpointsById.has(endpoint.id)) {
                throw new Error(`Duplicate command palette endpoint id: ${endpoint.id}`);
            }
            endpointsById.set(endpoint.id, endpoint);
        }

        for (const id of this._tagMap.keys()) {
            if (!endpointsById.has(id)) {
                throw new Error(`Tag config references unknown endpoint id: ${id}`);
            }
        }

        for (const endpoint of this._endpoints) {
            if (!this._tagMap.has(endpoint.id)) {
                throw new Error(`Endpoint ${endpoint.id} has no tag mapping in config`);
            }
            endpoint.tags = this._tagMap.get(endpoint.id);
        }
    }

    _ensureDom() {
        const existing = document.getElementById('command-palette-modal');
        if (existing) {
            this._elements = this._resolveElements(existing);
            return;
        }

        const modal = document.createElement('div');
        modal.id = 'command-palette-modal';
        modal.className = 'modal command-palette-modal';
        modal.style.display = 'none';
        modal.innerHTML = `
            <div class="command-palette-panel" role="dialog" aria-modal="true">
                <div class="command-palette-input-row">
                    <input
                        id="command-palette-input"
                        class="command-palette-input"
                        type="text"
                        autocomplete="off"
                        autocorrect="off"
                        autocapitalize="off"
                        spellcheck="false"
                        placeholder="Type tags…"
                    />
                </div>
                <div id="command-palette-suggestions" class="command-palette-suggestions"></div>
                <div id="command-palette-results" class="command-palette-results"></div>
            </div>
        `;
        document.body.appendChild(modal);
        this._elements = this._resolveElements(modal);
    }

    _resolveElements(modal) {
        const panel = modal.querySelector('.command-palette-panel');
        const input = modal.querySelector('#command-palette-input');
        const suggestions = modal.querySelector('#command-palette-suggestions');
        const results = modal.querySelector('#command-palette-results');

        if (!(panel instanceof HTMLElement)) {
            throw new Error('Command palette panel missing');
        }
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('Command palette input missing');
        }
        if (!(suggestions instanceof HTMLElement)) {
            throw new Error('Command palette suggestions missing');
        }
        if (!(results instanceof HTMLElement)) {
            throw new Error('Command palette results missing');
        }

        return { modal, panel, input, suggestions, results };
    }

    _applyPreferenceEffectsFromStorage() {
        const showTags = this._getBoolean('pref.show_note_tags', false);
        document.body.classList.toggle('pref-show-note-tags', showTags);

        const autoCollapse = this._getBoolean('pref.auto_collapse_long_notes', false);
        document.body.classList.toggle('pref-auto-collapse-long-notes', autoCollapse);

        const theme = this._getSelect('pref.theme', ['system', 'light', 'dark'], 'system');
        if (theme === 'system') {
            document.documentElement.removeAttribute('data-theme');
        } else {
            document.documentElement.setAttribute('data-theme', theme);
        }
    }

    _getBoolean(key, defaultValue) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('_getBoolean requires key string');
        }
        if (typeof defaultValue !== 'boolean') {
            throw new Error('_getBoolean requires defaultValue boolean');
        }

        const raw = this._preferences.getRaw(key);
        if (raw === null) {
            return defaultValue;
        }
        if (raw === 'true') {
            return true;
        }
        if (raw === 'false') {
            return false;
        }
        throw new Error(`Invalid stored boolean for ${key}`);
    }

    _getSelect(key, allowed, defaultValue) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('_getSelect requires key string');
        }
        if (!Array.isArray(allowed) || allowed.length === 0) {
            throw new Error('_getSelect requires allowed values array');
        }
        if (typeof defaultValue !== 'string' || defaultValue.length === 0) {
            throw new Error('_getSelect requires defaultValue string');
        }

        const raw = this._preferences.getRaw(key);
        if (raw === null) {
            return defaultValue;
        }
        if (!allowed.includes(raw)) {
            throw new Error(`Invalid stored select value for ${key}`);
        }
        return raw;
    }

    isOpen() {
        return this._isOpen;
    }

    async toggle() {
        if (!this._initialized) {
            await this.init();
        }

        if (this._isOpen) {
            this.close();
            return;
        }

        await this.open();
    }

    async open() {
        if (!this._initialized) {
            await this.init();
        }
        if (this._isOpen) {
            throw new Error('Command palette already open');
        }
        if (ModeContext.isLoading) {
            return;
        }
        if (ModeContext.modalStack && ModeContext.modalStack.length > 0) {
            return;
        }

        this._previousActiveElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        this._previousScrollY = Math.max(0, Math.round(window.scrollY));

        const modalStack = ensureModalStack();
        modalStack.push('commandPalette');

        const { modal, input } = this._elements;
        modal.style.display = 'block';
        this._isOpen = true;

        this._previousSelection.query = input.value;
        this._previousSelection.selectedIndex = 0;
        input.value = '';

        this._render();
        input.focus();

        document.addEventListener('keydown', this._handleKeyDown, { capture: true });
        input.addEventListener('input', this._handleInput);
        modal.addEventListener('click', this._handleClick);
    }

    close() {
        if (!this._isOpen) {
            throw new Error('Command palette is not open');
        }

        const { modal, input } = this._elements;
        modal.style.display = 'none';
        this._isOpen = false;

        document.removeEventListener('keydown', this._handleKeyDown, { capture: true });
        input.removeEventListener('input', this._handleInput);
        modal.removeEventListener('click', this._handleClick);

        const modalStack = ensureModalStack();
        const idx = modalStack.lastIndexOf('commandPalette');
        if (idx >= 0) {
            modalStack.splice(idx, 1);
        }

        if (typeof this._previousScrollY === 'number') {
            window.scrollTo(0, this._previousScrollY);
        }

        if (this._previousActiveElement) {
            this._previousActiveElement.focus();
        }

        this._previousActiveElement = null;
        this._previousScrollY = null;
    }

    _handleClick(event) {
        if (!event) {
            throw new Error('Command palette click handler missing event');
        }
        const { modal } = this._elements;
        if (event.target === modal) {
            this.close();
        }
    }

    _handleInput() {
        this._render();
    }

    async _handleKeyDown(event) {
        if (!event) {
            throw new Error('Command palette key handler missing event');
        }
        if (!this._isOpen) {
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            this.close();
            return;
        }

        if (event.key === 'ArrowDown') {
            event.preventDefault();
            event.stopPropagation();
            this._previousSelection.selectedIndex += 1;
            this._render();
            return;
        }

        if (event.key === 'ArrowUp') {
            event.preventDefault();
            event.stopPropagation();
            this._previousSelection.selectedIndex -= 1;
            this._render();
            return;
        }

        if (event.key === 'Enter') {
            event.preventDefault();
            event.stopPropagation();
            await this._activateSelected();
            return;
        }

        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault();
            event.stopPropagation();
            const direction = event.key === 'ArrowLeft' ? -1 : 1;
            await this._adjustSelected(direction);
        }
    }

    _render() {
        const { input, suggestions, results } = this._elements;
        const usageSnapshot = this._usage.getUsageSnapshot();

        const tokenization = tokenizeQuery(input.value);
        const committedTokens = tokenization.committed;
        const prefix = tokenization.prefix;

        const baseMatches = this._endpoints.filter((e) => endpointMatchesTags(e, committedTokens));

        let matches = baseMatches;
        if (typeof prefix === 'string' && prefix.length > 0) {
            matches = baseMatches.filter((e) => endpointMatchesPrefix(e, prefix));
        }

        if (committedTokens.length === 0) {
            matches = sortMatchesByUsage(matches, usageSnapshot);
        } else {
            matches = matches.slice().sort((a, b) => a.label.localeCompare(b.label));
        }

        const suggested = computeSuggestedTags(baseMatches, committedTokens, prefix, usageSnapshot);
        suggestions.innerHTML = '';
        for (const tag of suggested) {
            const el = document.createElement('span');
            el.className = 'command-palette-suggestion';
            el.textContent = tag;
            el.addEventListener('click', () => {
                const nextQuery = committedTokens.concat([tag]).join(' ') + ' ';
                input.value = nextQuery;
                this._previousSelection.selectedIndex = 0;
                this._render();
                input.focus();
            });
            suggestions.appendChild(el);
        }

        results.innerHTML = '';
        if (matches.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'command-palette-empty';

            const offender = this._findOffendingToken(committedTokens);
            if (offender) {
                empty.textContent = `No matches (try removing: ${offender})`;
            } else {
                empty.textContent = 'No matches';
            }
            results.appendChild(empty);

            let nearMissToken = null;
            if (typeof prefix === 'string' && prefix.length > 0) {
                nearMissToken = prefix;
            } else if (typeof offender === 'string' && offender.length > 0) {
                nearMissToken = offender;
            }

            const nearMisses = this._nearMissTags(nearMissToken);
            if (nearMisses.length > 0) {
                const hint = document.createElement('div');
                hint.className = 'command-palette-empty';
                hint.textContent = `Similar tags: ${nearMisses.join(', ')}`;
                results.appendChild(hint);
            }
            return;
        }

        const normalizedIndex = ((this._previousSelection.selectedIndex % matches.length) + matches.length) % matches.length;
        this._previousSelection.selectedIndex = normalizedIndex;

        for (let idx = 0; idx < matches.length; idx += 1) {
            const endpoint = matches[idx];
            const row = document.createElement('div');
            row.className = 'command-palette-row' + (idx === normalizedIndex ? ' selected' : '');
            row.dataset.endpointId = endpoint.id;

            const label = document.createElement('div');
            label.className = 'command-palette-row-label';
            label.textContent = endpoint.label;
            row.appendChild(label);

            const value = document.createElement('div');
            value.className = 'command-palette-row-value';
            value.textContent = this._formatEndpointValue(endpoint);
            row.appendChild(value);

            row.addEventListener('click', () => {
                this._previousSelection.selectedIndex = idx;
                this._render();
            });

            results.appendChild(row);
        }
    }

    _findOffendingToken(committedTokens) {
        if (!Array.isArray(committedTokens) || committedTokens.length === 0) {
            return null;
        }

        for (let idx = 0; idx < committedTokens.length; idx += 1) {
            const candidate = committedTokens[idx];
            const reduced = committedTokens.slice(0, idx).concat(committedTokens.slice(idx + 1));
            const matches = this._endpoints.filter((e) => endpointMatchesTags(e, reduced));
            if (matches.length > 0) {
                return candidate;
            }
        }
        return null;
    }

    _nearMissTags(token) {
        if (token === null || typeof token === 'undefined') {
            return [];
        }
        if (typeof token !== 'string' || token.length === 0) {
            return [];
        }

        const maxResults = 8;
        const lower = token.toLowerCase();
        const prefixMatches = [];
        for (const tag of this._allTags) {
            if (tag.startsWith(lower)) {
                prefixMatches.push(tag);
            }
        }
        prefixMatches.sort();
        if (prefixMatches.length > 0) {
            return prefixMatches.slice(0, maxResults);
        }

        const editMatches = [];
        for (const tag of this._allTags) {
            if (this._editDistanceAtMostOne(lower, tag)) {
                editMatches.push(tag);
            }
        }
        editMatches.sort();
        return editMatches.slice(0, maxResults);
    }

    _editDistanceAtMostOne(a, b) {
        if (typeof a !== 'string' || typeof b !== 'string') {
            throw new Error('_editDistanceAtMostOne requires strings');
        }
        if (a === b) {
            return true;
        }
        const lenDiff = Math.abs(a.length - b.length);
        if (lenDiff > 1) {
            return false;
        }

        const shorter = a.length <= b.length ? a : b;
        const longer = a.length <= b.length ? b : a;

        let i = 0;
        let j = 0;
        let edits = 0;
        while (i < shorter.length && j < longer.length) {
            if (shorter[i] === longer[j]) {
                i += 1;
                j += 1;
                continue;
            }
            edits += 1;
            if (edits > 1) {
                return false;
            }
            if (shorter.length === longer.length) {
                i += 1;
                j += 1;
            } else {
                j += 1;
            }
        }
        if (i < shorter.length || j < longer.length) {
            edits += 1;
        }
        return edits <= 1;
    }

    _formatEndpointValue(endpoint) {
        if (endpoint.kind === 'boolean') {
            const value = this._getBoolean(endpoint.persistenceKey, endpoint.defaultValue);
            return value ? '[x]' : '[ ]';
        }
        if (endpoint.kind === 'select') {
            const allowed = endpoint.options.map((o) => o.value);
            const raw = this._getSelect(endpoint.persistenceKey, allowed, endpoint.defaultValue);
            const option = endpoint.options.find((o) => o.value === raw);
            return option ? option.label : raw;
        }
        if (endpoint.kind === 'action') {
            return '↵';
        }
        if (endpoint.kind === 'form') {
            return '…';
        }
        return '';
    }

    _getVisibleMatches() {
        const { input } = this._elements;
        const tokenization = tokenizeQuery(input.value);
        const committed = tokenization.committed;
        const prefix = tokenization.prefix;
        const usageSnapshot = this._usage.getUsageSnapshot();

        const baseMatches = this._endpoints.filter((e) => endpointMatchesTags(e, committed));
        let matches = baseMatches;
        if (typeof prefix === 'string' && prefix.length > 0) {
            matches = baseMatches.filter((e) => endpointMatchesPrefix(e, prefix));
        }

        if (committed.length === 0) {
            matches = sortMatchesByUsage(matches, usageSnapshot);
        } else {
            matches = matches.slice().sort((a, b) => a.label.localeCompare(b.label));
        }
        return matches;
    }

    async _activateSelected() {
        const matches = this._getVisibleMatches();
        if (matches.length === 0) {
            return;
        }
        const idx = this._previousSelection.selectedIndex;
        const normalized = ((idx % matches.length) + matches.length) % matches.length;
        const endpoint = matches[normalized];

        const tokenization = tokenizeQuery(this._elements.input.value);

        const usageTokens = [];
        for (const token of tokenization.committed) {
            usageTokens.push(token);
        }
        if (typeof tokenization.prefix === 'string' && tokenization.prefix.length > 0) {
            usageTokens.push(tokenization.prefix);
        }
        this._usage.recordUse(endpoint.id, usageTokens);

        if (endpoint.kind === 'boolean') {
            const current = this._getBoolean(endpoint.persistenceKey, endpoint.defaultValue);
            await endpoint.apply(!current);
            this._render();
            return;
        }
        if (endpoint.kind === 'select') {
            const allowed = endpoint.options.map((o) => o.value);
            const current = this._getSelect(endpoint.persistenceKey, allowed, endpoint.defaultValue);
            const next = endpoint.options.findIndex((o) => o.value === current);
            const index = next >= 0 ? (next + 1) % endpoint.options.length : 0;
            await endpoint.apply(endpoint.options[index].value);
            this._render();
            return;
        }
        if (typeof endpoint.execute === 'function') {
            await endpoint.execute();
            this._render();
        }
    }

    async _adjustSelected(direction) {
        if (direction !== -1 && direction !== 1) {
            throw new Error('_adjustSelected requires direction -1 or 1');
        }
        const matches = this._getVisibleMatches();
        if (matches.length === 0) {
            return;
        }
        const idx = this._previousSelection.selectedIndex;
        const normalized = ((idx % matches.length) + matches.length) % matches.length;
        const endpoint = matches[normalized];
        if (endpoint.kind !== 'select') {
            return;
        }

        const allowed = endpoint.options.map((o) => o.value);
        const current = this._getSelect(endpoint.persistenceKey, allowed, endpoint.defaultValue);
        const currentIndex = endpoint.options.findIndex((o) => o.value === current);
        const baseIndex = currentIndex >= 0 ? currentIndex : 0;
        const nextIndex = ((baseIndex + direction) % endpoint.options.length + endpoint.options.length) % endpoint.options.length;
        await endpoint.apply(endpoint.options[nextIndex].value);
        this._render();
    }

    applyPreference(prefKey, value) {
        if (typeof prefKey !== 'string' || prefKey.length === 0) {
            throw new Error('applyPreference requires prefKey string');
        }
        if (typeof value === 'boolean') {
            this._preferences.setRaw(prefKey, value ? 'true' : 'false');
            this._applyPreferenceEffectsFromStorage();
            return;
        }
        if (typeof value === 'string') {
            this._preferences.setRaw(prefKey, value);
            this._applyPreferenceEffectsFromStorage();
            return;
        }
        throw new Error('applyPreference requires boolean or string value');
    }

    async resetAllPreferences() {
        this._preferences.clearAll();
        this._applyPreferenceEffectsFromStorage();
    }

    async resetViewFilters() {
        if (ModeContext.isEditing) {
            await actionSaveAndExitEditingWithoutRefreshing();
        }

        const searchInput = document.getElementById('search-input');
        if (!(searchInput instanceof HTMLInputElement)) {
            throw new Error('search-input missing from DOM');
        }
        const analysis = syncSearchInputValue(searchInput, '');
        ModeContext.setSearchQuery(analysis.normalizedText);
        ModeContext.clearActiveTabDiffCacheForSearchExecution(analysis.normalizedText);
        ModeContext.resetRootTracking({ clear: true });
        window.scrollTo(0, 0);
        ModeContext.updateActiveTabScroll(0);
        ModeContext.updateActiveTabScrollAnchor(null, true);
        ModeContext.setRootAnchorId(null);

        await actionRefreshAndMaybeSelect({});
    }

    async collapseAll() {
        if (ModeContext.isEditing) {
            await actionSaveAndExitEditingWithoutRefreshing();
        }

        const searchQuery = ModeContext.searchQuery;
        if (typeof searchQuery !== 'string') {
            throw new Error('ModeContext.searchQuery must be a string');
        }

        ModeContext.setLoading(true);
        await NotesAPI.setCollapsedInContext(searchQuery, true).finally(() => {
            if (ModeContext.isLoading) {
                ModeContext.setLoading(false);
            }
        });
        await actionRefreshAndMaybeSelect({});
    }

    async expandAll() {
        if (ModeContext.isEditing) {
            await actionSaveAndExitEditingWithoutRefreshing();
        }

        const searchQuery = ModeContext.searchQuery;
        if (typeof searchQuery !== 'string') {
            throw new Error('ModeContext.searchQuery must be a string');
        }

        ModeContext.setLoading(true);
        await NotesAPI.setCollapsedInContext(searchQuery, false).finally(() => {
            if (ModeContext.isLoading) {
                ModeContext.setLoading(false);
            }
        });
        await actionRefreshAndMaybeSelect({});
    }

    async openPasswordManager() {
        if (ModeContext.isEditing) {
            await actionSaveAndExitEditingWithoutRefreshing();
        }
        if (ModeContext.isSearching) {
            ModeContext.setSearching(false);
        }

        const restoreQuery = this._elements.input.value;
        const restoreIndex = this._previousSelection.selectedIndex;
        this.close();

        const modalClosedHandler = (event) => {
            const detail = event && event.detail && typeof event.detail === 'object' ? event.detail : null;
            if (!detail || detail.modalName !== 'passwordModal') {
                return;
            }
            document.removeEventListener('metalist:modal-closed', modalClosedHandler);
            void this.open().then(() => {
                this._elements.input.value = restoreQuery;
                this._previousSelection.selectedIndex = restoreIndex;
                this._render();
            });
        };
        document.addEventListener('metalist:modal-closed', modalClosedHandler);

        const passwordModal = new PasswordModal();
        passwordModal.open();
    }
}

export const CommandPalette = new CommandPaletteController();
