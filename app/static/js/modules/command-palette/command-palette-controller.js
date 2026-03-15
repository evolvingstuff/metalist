import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';
import { actionRefreshAndMaybeSelect, showPerfOverlayFromCache } from '../mode-manager/actions/ui-actions.js';
import { actionSaveAndExitEditingWithoutRefreshing } from '../mode-manager/actions/selection-actions.js';
import { FilesAPI, NotesAPI } from '../api-client.js';
import { CONFIG } from '../config.js';
import { ErrorHandler } from '../error-handler.js';
import { PasswordModal } from '../modals/password-modal.js';
import { BackupRetentionModal } from '../modals/backup-retention-modal.js';
import { BackupResultModal } from '../modals/backup-result-modal.js';
import { BackupRestoreModal } from '../modals/backup-restore-modal.js';
import { OntologyModal } from '../modals/ontology-modal.js';
import { RandomPasswordModal } from '../modals/random-password-modal.js';
import { HelpModal } from '../modals/help-modal.js';
import { NamespaceSwitcherModal } from '../modals/namespace-switcher-modal.js';
import { DeleteNamespaceModal } from '../modals/delete-namespace-modal.js';
import { syncSearchInputValue } from '../mode-manager/services/search-input-service.js';
import { CommandGate } from '../mode-manager/services/command-gate-service.js';
import { cancelDebouncedSearchExecution } from '../mode-manager/services/search-debounce-service.js';
import { refreshBacklinksPanel, invalidateBacklinksPanelCache } from '../mode-manager/services/backlinks-panel-service.js';
import { attachPickedFileToCurrentNote, pickFileForAttachment } from '../mode-manager/services/file-reference-service.js';

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

        this._ontologyModal = null;
        this._backupRetentionModal = null;
        this._backupResultModal = null;
        this._backupRestoreModal = null;
        this._randomPasswordModal = null;
        this._helpModal = null;
        this._namespaceSwitcherModal = null;
        this._deleteNamespaceModal = null;

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
                openOntologyEditor: this.openOntologyEditor.bind(this),
                createBackup: this.createBackup.bind(this),
                openBackupRestore: this.openBackupRestore.bind(this),
                logout: this.logout.bind(this),
                openRandomPasswordGenerator: this.openRandomPasswordGenerator.bind(this),
                collapseAll: this.collapseAll.bind(this),
                expandAll: this.expandAll.bind(this),
                resetViewFilters: this.resetViewFilters.bind(this),
                resetAllPreferences: this.resetAllPreferences.bind(this),
                runMcpClient: this.runMcpClient.bind(this),
                openKeyboardShortcutsHelp: this.openKeyboardShortcutsHelp.bind(this),
                attachFileToCurrentNote: this.attachFileToCurrentNote.bind(this),
                trimUnusedFiles: this.trimUnusedFiles.bind(this),
                openNamespaceSwitcher: this.openNamespaceSwitcher.bind(this),
                openDeleteCurrentNamespace: this.openDeleteCurrentNamespace.bind(this),
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
        const showBacklinks = this._getBoolean('pref.show_backlinks', true);
        document.body.classList.toggle('pref-show-backlinks', showBacklinks);

        const showTags = this._getBoolean('pref.show_note_tags', false);
        document.body.classList.toggle('pref-show-note-tags', showTags);

        const showTabUi = this._getBoolean('pref.show_tab_ui', false);
        document.body.classList.toggle('pref-show-tab-ui', showTabUi);

        const autoCollapse = this._getBoolean('pref.auto_collapse_long_notes', false);
        document.body.classList.toggle('pref-auto-collapse-long-notes', autoCollapse);

        const showPerfOverlay = this._getBoolean('pref.show_perf_overlay', false);
        document.body.classList.toggle('pref-show-perf-overlay', showPerfOverlay);
        if (!showPerfOverlay) {
            const perfOverlay = document.getElementById('perf-overlay');
            if (perfOverlay) {
                perfOverlay.remove();
            }
        }

        const theme = this._getSelect('pref.theme', ['system', 'light', 'dark'], 'system');
        if (theme === 'system') {
            document.documentElement.removeAttribute('data-theme');
        } else {
            document.documentElement.setAttribute('data-theme', theme);
        }

        const tabIndicator = document.getElementById('tab-indicator');
        if (tabIndicator) {
            tabIndicator.style.display = 'none';
        }

        const searchContextsList = document.getElementById('search-contexts-list');
        if (searchContextsList) {
            if (showTabUi) {
                if (searchContextsList.innerHTML.trim().length > 0) {
                    searchContextsList.style.display = 'block';
                }
            } else {
                searchContextsList.style.display = 'none';
            }
        }

        invalidateBacklinksPanelCache();
        void refreshBacklinksPanel({ force: true });
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

        // Entering the command palette is a global context boundary.
        // Any subsequent undo/redo should not traverse operations from before.
        ModeContext.bumpUndoContextEpoch('commandPalette.open');
        cancelDebouncedSearchExecution();

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

            row.addEventListener('click', async () => {
                this._previousSelection.selectedIndex = idx;
                await this._activateSelected();
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

    async applyPreference(prefKey, value) {
        if (typeof prefKey !== 'string' || prefKey.length === 0) {
            throw new Error('applyPreference requires prefKey string');
        }
        if (typeof value === 'boolean') {
            this._preferences.setRaw(prefKey, value ? 'true' : 'false');
            this._applyPreferenceEffectsFromStorage();
            if (prefKey === 'pref.show_perf_overlay' && value) {
                const hadCache = showPerfOverlayFromCache();
                if (!hadCache) {
                    await actionRefreshAndMaybeSelect({
                        startedAt: performance.now(),
                        context: 'pref.show_perf_overlay',
                    });
                }
            }
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

    async runMcpClient() {
        const mcpClientUrl = `${window.location.origin}/mcp-client-v2`;

        if (this.isOpen()) {
            this.close();
        }

        window.open(mcpClientUrl, '_blank', 'noopener,noreferrer');
    }

    async attachFileToCurrentNote() {
        if (this.isOpen()) {
            this.close();
        }

        try {
            const preferredNoteId = ModeContext.isEditing ? ModeContext.currentNoteId : null;
            const file = await pickFileForAttachment();
            if (file === null) {
                ErrorHandler.showInfoBanner('Attach file canceled or no file was selected.', 5000);
                return;
            }

            const result = await CommandGate.run('commandPalette.attachFileToCurrentNote', async () => {
                return await attachPickedFileToCurrentNote(file, preferredNoteId);
            }, {
                timeoutMs: 120000,
            });
            if (result === null) {
                ErrorHandler.showErrorBanner(
                    'Attach file did not start because another command is still running.',
                    'error',
                    10000,
                    true,
                );
            }
        } catch (error) {
            if (
                error instanceof Error
                && (error.message.includes('File upload failed:') || error.message.includes('API call failed:'))
            ) {
                throw error;
            }
            const message = error instanceof Error ? error.message : 'Unknown error';
            console.error('Attach file failed:', error);
            ErrorHandler.showErrorBanner(
                `Attach file failed: ${message}`,
                'error',
                10000,
                true,
            );
        }
    }

    async trimUnusedFiles() {
        if (this.isOpen()) {
            this.close();
        }

        const confirmed = window.confirm(
            'Trim all files that are not referenced by any saved note? This cannot be undone.',
        );
        if (!confirmed) {
            return;
        }

        const result = await CommandGate.run('commandPalette.trimUnusedFiles', async () => {
            if (ModeContext.isEditing) {
                await actionSaveAndExitEditingWithoutRefreshing();
            }

            const payload = await FilesAPI.trimUnusedFiles();
            if (!payload || typeof payload !== 'object') {
                throw new Error('Trim unused files response missing body');
            }
            if (!Number.isInteger(payload.deleted_count) || payload.deleted_count < 0) {
                throw new Error('Trim unused files response missing deleted_count');
            }
            if (!Array.isArray(payload.deleted_file_ids)) {
                throw new Error('Trim unused files response missing deleted_file_ids');
            }

            await actionRefreshAndMaybeSelect({});
            return payload;
        });
        if (result === null) {
            return;
        }

        window.alert(`Trimmed ${result.deleted_count} unused file(s).`);
    }

    async resetViewFilters() {
        const result = await CommandGate.run('commandPalette.resetViewFilters', async () => {
            ModeContext.bumpUndoContextEpoch('commandPalette.resetViewFilters');

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
        });
        if (result === null) {
            return;
        }
    }

    async collapseAll() {
        const result = await CommandGate.run('commandPalette.collapseAll', async () => {
            ModeContext.bumpUndoContextEpoch('commandPalette.collapseAll');

            if (ModeContext.isEditing) {
                await actionSaveAndExitEditingWithoutRefreshing();
            }

            const searchQuery = ModeContext.searchQuery;
            if (typeof searchQuery !== 'string') {
                throw new Error('ModeContext.searchQuery must be a string');
            }

            await NotesAPI.setCollapsedInContext(searchQuery, true);
            await actionRefreshAndMaybeSelect({});
        });
        if (result === null) {
            return;
        }
    }

    async expandAll() {
        const result = await CommandGate.run('commandPalette.expandAll', async () => {
            ModeContext.bumpUndoContextEpoch('commandPalette.expandAll');

            if (ModeContext.isEditing) {
                await actionSaveAndExitEditingWithoutRefreshing();
            }

            const searchQuery = ModeContext.searchQuery;
            if (typeof searchQuery !== 'string') {
                throw new Error('ModeContext.searchQuery must be a string');
            }

            await NotesAPI.setCollapsedInContext(searchQuery, false);
            await actionRefreshAndMaybeSelect({});
        });
        if (result === null) {
            return;
        }
    }

    _buildAuthHeaders(includeContentType) {
        if (typeof includeContentType !== 'boolean') {
            throw new Error('_buildAuthHeaders requires boolean includeContentType');
        }

        const tabId = sessionStorage.getItem('metalist_tab_id');
        if (typeof tabId !== 'string' || tabId.length === 0) {
            throw new Error('metalist_tab_id missing from sessionStorage');
        }

        const token = localStorage.getItem('auth_token');
        if (typeof token !== 'string' || token.length === 0) {
            throw new Error('auth_token missing from localStorage');
        }

        const headers = {
            Authorization: `Bearer ${token}`,
            'X-Metalist-Tab-Id': tabId,
        };
        if (includeContentType) {
            headers['Content-Type'] = 'application/json';
        }
        return headers;
    }

    async _authRequest(url, method, bodyObject) {
        if (typeof url !== 'string' || url.length === 0) {
            throw new Error('_authRequest requires url string');
        }
        if (typeof method !== 'string' || method.length === 0) {
            throw new Error('_authRequest requires method string');
        }
        if (bodyObject !== null && typeof bodyObject !== 'object') {
            throw new Error('_authRequest bodyObject must be object or null');
        }

        const hasBody = bodyObject !== null;
        const response = await fetch(url, {
            method,
            headers: this._buildAuthHeaders(hasBody),
            body: hasBody ? JSON.stringify(bodyObject) : undefined,
        });

        let payload = null;
        const contentType = response.headers.get('content-type');
        if (typeof contentType === 'string' && contentType.includes('application/json')) {
            payload = await response.json();
        }

        if (!response.ok) {
            if (payload && typeof payload === 'object' && typeof payload.detail === 'string') {
                throw new Error(`Request failed (${response.status}): ${payload.detail}`);
            }
            throw new Error(`Request failed (${response.status})`);
        }

        if (payload === null) {
            throw new Error('Response payload missing');
        }
        return payload;
    }

    _clearSessionState() {
        localStorage.removeItem('auth_token');
        sessionStorage.removeItem('metalist_client_id');
        localStorage.removeItem('auth_owner');
    }

    _getBackupRetentionPromptThreshold() {
        const threshold = CONFIG.BACKUP.RETENTION_PROMPT_THRESHOLD;
        if (!Number.isInteger(threshold) || threshold <= 0) {
            throw new Error('CONFIG.BACKUP.RETENTION_PROMPT_THRESHOLD must be a positive integer');
        }
        return threshold;
    }

    _getBackupRetentionSuggestedKeepCount() {
        const suggestedKeepCount = CONFIG.BACKUP.RETENTION_SUGGESTED_KEEP_COUNT;
        if (!Number.isInteger(suggestedKeepCount) || suggestedKeepCount <= 0) {
            throw new Error('CONFIG.BACKUP.RETENTION_SUGGESTED_KEEP_COUNT must be a positive integer');
        }
        return suggestedKeepCount;
    }

    async _listBackupsForRetentionPrompt() {
        const payload = await this._authRequest(CONFIG.API.AUTH.BACKUP.LIST, 'GET', null);
        if (!payload || typeof payload !== 'object') {
            throw new Error('Backup list response missing body');
        }
        if (!Array.isArray(payload.backups)) {
            throw new Error('Backup list response missing backups array');
        }
        return payload.backups;
    }

    async _openBackupRetentionModal(retentionContext) {
        if (!retentionContext || typeof retentionContext !== 'object') {
            throw new Error('_openBackupRetentionModal requires retentionContext object');
        }
        if (this._backupRetentionModal === null) {
            this._backupRetentionModal = new BackupRetentionModal();
        }

        if (this.isOpen()) {
            this.close();
        }
        if (ModeContext.isSearching) {
            ModeContext.setSearching(false);
        }

        return await this._backupRetentionModal.openForBackup(retentionContext);
    }

    async _openBackupResultModal(resultContext) {
        if (!resultContext || typeof resultContext !== 'object') {
            throw new Error('_openBackupResultModal requires resultContext object');
        }
        if (this._backupResultModal === null) {
            this._backupResultModal = new BackupResultModal();
        }
        if (this.isOpen()) {
            this.close();
        }
        if (ModeContext.isSearching) {
            ModeContext.setSearching(false);
        }

        await this._backupResultModal.openWithResult(resultContext);
    }

    async _maybeDeleteOldestBackupsAfterCreate(createdFilename) {
        if (typeof createdFilename !== 'string' || createdFilename.length === 0) {
            throw new Error('_maybeDeleteOldestBackupsAfterCreate requires createdFilename');
        }

        const backups = await this._listBackupsForRetentionPrompt();
        const backupCount = backups.length;
        const threshold = this._getBackupRetentionPromptThreshold();
        if (backupCount < threshold) {
            return {
                deletedCount: 0,
                remainingCount: backupCount,
            };
        }
        const suggestedKeepCount = this._getBackupRetentionSuggestedKeepCount();

        const modalResult = await this._openBackupRetentionModal({
            createdFilename,
            backupCount,
            suggestedKeepCount,
        });
        if (!modalResult || typeof modalResult !== 'object') {
            throw new Error('Retention modal result missing');
        }

        if (modalResult.action !== 'apply') {
            return {
                deletedCount: 0,
                remainingCount: backupCount,
            };
        }
        if (!Number.isInteger(modalResult.keepCount)) {
            throw new Error('Retention modal result missing keepCount');
        }

        const keepCount = modalResult.keepCount;
        if (keepCount < 1 || keepCount > backupCount) {
            throw new Error(`keepCount out of range: ${keepCount}`);
        }

        const deleteCount = backupCount - keepCount;
        if (deleteCount <= 0) {
            return {
                deletedCount: 0,
                remainingCount: backupCount,
            };
        }

        const payload = await this._authRequest(CONFIG.API.AUTH.BACKUP.DELETE_OLDEST, 'POST', {
            count: deleteCount,
        });
        if (!payload || typeof payload !== 'object') {
            throw new Error('Backup delete response missing body');
        }
        if (!Array.isArray(payload.deleted_backups)) {
            throw new Error('Backup delete response missing deleted_backups array');
        }
        const deletedCount = payload.deleted_backups.length;
        const remainingCount = backupCount - deletedCount;
        if (remainingCount < 0) {
            throw new Error(`remainingCount must be non-negative, got ${remainingCount}`);
        }
        return {
            deletedCount,
            remainingCount,
        };
    }

    async createBackup() {
        if (this.isOpen()) {
            this.close();
        }

        const createdFilename = await CommandGate.run('commandPalette.createBackup', async () => {
            if (ModeContext.isEditing) {
                await actionSaveAndExitEditingWithoutRefreshing();
            }

            const payload = await this._authRequest(CONFIG.API.AUTH.BACKUP.CREATE, 'POST', null);
            if (!payload || typeof payload !== 'object') {
                throw new Error('Backup response missing body');
            }
            if (!payload.backup || typeof payload.backup !== 'object') {
                throw new Error('Backup response missing backup object');
            }
            if (typeof payload.backup.filename !== 'string' || payload.backup.filename.length === 0) {
                throw new Error('Backup response missing filename');
            }

            return payload.backup.filename;
        });
        if (createdFilename === null) {
            return;
        }
        if (typeof createdFilename !== 'string' || createdFilename.length === 0) {
            throw new Error('createBackup expected created filename from CommandGate');
        }

        const retentionResult = await this._maybeDeleteOldestBackupsAfterCreate(createdFilename);

        if (!retentionResult || typeof retentionResult !== 'object') {
            throw new Error('Retention result missing');
        }
        if (!Number.isInteger(retentionResult.deletedCount) || retentionResult.deletedCount < 0) {
            throw new Error('Retention result has invalid deletedCount');
        }
        if (!Number.isInteger(retentionResult.remainingCount) || retentionResult.remainingCount < 0) {
            throw new Error('Retention result has invalid remainingCount');
        }

        await this._openBackupResultModal({
            createdFilename,
            deletedCount: retentionResult.deletedCount,
            remainingCount: retentionResult.remainingCount,
        });
    }

    async logout() {
        const result = await CommandGate.run('commandPalette.logout', async () => {
            if (ModeContext.isEditing) {
                await actionSaveAndExitEditingWithoutRefreshing();
            }

            const token = localStorage.getItem('auth_token');
            const tabId = sessionStorage.getItem('metalist_tab_id');
            if (typeof token === 'string' && token.length > 0 && typeof tabId === 'string' && tabId.length > 0) {
                await fetch(CONFIG.API.AUTH.LOGOUT, {
                    method: 'POST',
                    headers: {
                        Authorization: `Bearer ${token}`,
                        'Content-Type': 'application/json',
                        'X-Metalist-Tab-Id': tabId,
                    },
                }).finally(() => {
                    this._clearSessionState();
                    window.location.reload();
                });
                return;
            }

            this._clearSessionState();
            window.location.reload();
        });
        if (result === null) {
            return;
        }
    }

    async openBackupRestore() {
        if (ModeContext.isEditing) {
            await actionSaveAndExitEditingWithoutRefreshing();
        }
        if (ModeContext.isSearching) {
            ModeContext.setSearching(false);
        }
        this.close();

        if (this._backupRestoreModal === null) {
            this._backupRestoreModal = new BackupRestoreModal();
        }
        this._backupRestoreModal.open();
    }

    async openRandomPasswordGenerator() {
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
            if (!detail || detail.modalName !== 'randomPasswordModal') {
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

        if (this._randomPasswordModal === null) {
            this._randomPasswordModal = new RandomPasswordModal();
        }
        this._randomPasswordModal.open();
    }

    async openOntologyEditor() {
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
            if (!detail || detail.modalName !== 'ontologyModal') {
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

        if (this._ontologyModal === null) {
            this._ontologyModal = new OntologyModal();
        }
        this._ontologyModal.open();
    }

    async openKeyboardShortcutsHelp() {
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
            if (!detail || detail.modalName !== 'help') {
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

        if (this._helpModal === null) {
            this._helpModal = new HelpModal();
        }
        this._helpModal.open();
    }

    async openNamespaceSwitcher() {
        if (ModeContext.isEditing) {
            await actionSaveAndExitEditingWithoutRefreshing();
        }
        if (ModeContext.isSearching) {
            ModeContext.setSearching(false);
        }
        this.close();

        if (this._namespaceSwitcherModal === null) {
            this._namespaceSwitcherModal = new NamespaceSwitcherModal();
        }
        this._namespaceSwitcherModal.open();
    }

    async openDeleteCurrentNamespace() {
        if (ModeContext.isEditing) {
            await actionSaveAndExitEditingWithoutRefreshing();
        }
        if (ModeContext.isSearching) {
            ModeContext.setSearching(false);
        }
        this.close();

        if (this._deleteNamespaceModal === null) {
            this._deleteNamespaceModal = new DeleteNamespaceModal();
        }
        this._deleteNamespaceModal.open();
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
