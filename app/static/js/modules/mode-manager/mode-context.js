import * as Logger from './mode-logger.js';
import { CONFIG } from '../config.js';
import { restoreScrollFromAnchor } from './services/scroll-restoration-service.js';

class ModeContext {
    constructor() {
                
        this._editing = false;     
        this._searching = false;
        this._active = true;       
        this._dirty = false;       
        this._loading = false;     
        this._loadingTimeoutId = null;
        this._loadingNotifyTimeoutId = null;
        this._loadingStartedAt = null;

        this._currentNoteId = null;     
        this._lastSavedContent = null;  
        this._cursorOffset = null;      
        this._searchQuery = null;       
        this._currentContent = null;    

        this._lastKeyPressed = null;    
        this._lastClickTarget = null;   
        this._metaKeyPressed = false;   
        this._shiftKeyPressed = false;  
        this._hoveredNoteId = null;
        this._caretHidden = false;

        // Tracks whether this edit session has created editor undo history.
        // This is intentionally separate from "dirty" because autosave can clear dirty
        // while the editor still has undo history.
        this._editSessionHasEdits = false;

        this._listeners = [];
        this._lastContentChangeTime = null;
        this._searchQuery = '';
        this._isInitialPageLoad = true;
        
        // Tab state management
        this._activeTabId = '0';
        this._tabs = {
            '0': { searchQuery: '', scrollY: 0, scrollAnchor: null }
        };
        this._tabRootAnchors = Object.create(null);
        
        // Multi-device sync
        this._clientId = this._generateClientId();
        this._lastUpdateUUID = null;
        
        // Clipboard mode tracking
        this._clipboardMode = 'system'; // 'system' for text, 'note' for note copying
        
        // Connection state tracking
        this._isConnected = true;
        this._connectionErrorBannerVisible = false;
        
        // User activity tracking for token refresh
        this._userActivity = false;

        // Diff protocol cache per tab + per-tab root tracking
        this._tabNoteHashes = Object.create(null);
        this._tabKnownRootIds = Object.create(null);
        this._tabSeenRootIds = Object.create(null);
        this._tabRootOrder = Object.create(null);
        this._ensureTabContainers(this._activeTabId);
        this._lowestVisibleRootId = null;

        // asdf hack
        this._requestStartedAt = null;

        this._tabStateUpdateHook = null;
        this._tabStateVersion = 0;
        this._ignoreScrollEventsDepth = 0;
    }

    _ensureTabContainers(tabId) {
        if (!this._tabNoteHashes[tabId]) {
            this._tabNoteHashes[tabId] = new Map();
        }
        if (!this._tabKnownRootIds[tabId]) {
            this._tabKnownRootIds[tabId] = new Set();
        }
        if (!this._tabSeenRootIds[tabId]) {
            this._tabSeenRootIds[tabId] = new Set();
        }
        if (!this._tabRootAnchors[tabId]) {
            this._tabRootAnchors[tabId] = null;
        }
        if (!Array.isArray(this._tabRootOrder[tabId])) {
            this._tabRootOrder[tabId] = [];
        }
    }

    _ensureTabNoteHashes(tabId) {
        this._ensureTabContainers(tabId);
        return this._tabNoteHashes[tabId];
    }

    _getActiveNoteHashes() {
        return this._ensureTabNoteHashes(this._activeTabId);
    }

    _getActiveKnownRoots() {
        this._ensureTabContainers(this._activeTabId);
        return this._tabKnownRootIds[this._activeTabId];
    }

    _getActiveSeenRoots() {
        this._ensureTabContainers(this._activeTabId);
        return this._tabSeenRootIds[this._activeTabId];
    }

    hasNoteHash(noteId) {
        if (!noteId) {
            throw new Error('noteId is required for hasNoteHash');
        }
        return this._getActiveNoteHashes().has(noteId);
    }

    getNoteHash(noteId) {
        if (!noteId) {
            throw new Error('noteId is required for getNoteHash');
        }
        const noteHashes = this._getActiveNoteHashes();
        if (!noteHashes.has(noteId)) {
            throw new Error(`Hash for note ${noteId} is not cached`);
        }
        return noteHashes.get(noteId);
    }

    setNoteHash(noteId, hash) {
        if (!noteId) {
            throw new Error('noteId is required for setNoteHash');
        }
        if (typeof hash !== 'string' || hash.length === 0) {
            throw new Error('hash must be a non-empty string');
        }
        this._getActiveNoteHashes().set(noteId, hash);
        return this;
    }

    removeNoteHash(noteId) {
        if (!noteId) {
            throw new Error('noteId is required for removeNoteHash');
        }
        this._getActiveNoteHashes().delete(noteId);
        return this;
    }

    clearNoteHashes() {
        this._getActiveNoteHashes().clear();
        return this;
    }

    clearTabViewCache(tabId) {
        if (typeof tabId !== 'string' || tabId.length === 0) {
            throw new Error('tabId must be a non-empty string');
        }
        this._ensureTabContainers(tabId);
        this._tabNoteHashes[tabId].clear();
        this._tabKnownRootIds[tabId].clear();
        this._tabSeenRootIds[tabId].clear();
        this._tabRootOrder[tabId] = [];
        this._tabRootAnchors[tabId] = null;
        return this;
    }

    clearAllTabViewCaches() {
        const tabIds = new Set([
            ...Object.keys(this._tabs || {}),
            ...Object.keys(this._tabNoteHashes || {}),
        ]);
        for (const tabId of tabIds) {
            this.clearTabViewCache(tabId);
        }
        return this;
    }

    getNoteHashPayload() {
        const payload = {};
        for (const [noteId, hash] of this._getActiveNoteHashes().entries()) {
            payload[noteId] = hash;
        }
        return payload;
    }

    syncNoteHashesFromSnapshot(snapshot) {
        if (!snapshot || !Array.isArray(snapshot.structure)) {
            throw new Error('Invalid snapshot payload');
        }

        const validIds = new Set();
        const noteHashes = this._getActiveNoteHashes();
        for (const entry of snapshot.structure) {
            if (!entry || typeof entry !== 'object') {
                throw new Error('Malformed structure entry in snapshot');
            }
            const { id, hash } = entry;
            if (typeof id !== 'string' || typeof hash !== 'string' || !hash) {
                throw new Error('Structure entry missing id/hash');
            }
            validIds.add(id);
            noteHashes.set(id, hash);
        }

        for (const noteId of Array.from(noteHashes.keys())) {
            if (!validIds.has(noteId)) {
                noteHashes.delete(noteId);
            }
        }

        this._updateRootTracking(snapshot.structure);

        return this;
    }

    syncRootIds(rootIds) {
        if (!Array.isArray(rootIds)) {
            return this;
        }

        const knownRoots = this._getActiveKnownRoots();
        knownRoots.clear();
        const order = [];
        for (const id of rootIds) {
            if (typeof id === 'string' && id) {
                knownRoots.add(id);
                order.push(id);
            }
        }

        const intersectedSeen = new Set();
        const seenRoots = this._getActiveSeenRoots();
        for (const rootId of seenRoots) {
            if (knownRoots.has(rootId)) {
                intersectedSeen.add(rootId);
            }
        }
        const active = this._activeTabId;
        this._tabSeenRootIds[active] = intersectedSeen;
        this._tabRootOrder[active] = order;

        queueMicrotask(async () => {
            const module = await import('./services/infinite-scroll-service.js');
            module.refreshOverlayMetrics();
        });

        return this;
    }

    setEditing(value) {
                
        if (this._editing === value) {
            throw new Error(`Redundant state change: editing is already ${value}`);
        }
                
        const oldValue = this._editing;
        this._editing = Boolean(value);

        this._editSessionHasEdits = false;
        if (!this._editing) {
            this._caretHidden = false;
        }
        
        if (oldValue !== this._editing) {
            this._notifyListeners('editing', this._editing);
        }
                
        return this;
    }

    get isEditing() {
        return this._editing;
    }

    get noteCount() {
        return this._getActiveNoteHashes().size;
    }

    markEditSessionHasEdits() {
        if (!this._editSessionHasEdits) {
            this._editSessionHasEdits = true;
        }
        return this;
    }

    get editSessionHasEdits() {
        return Boolean(this._editSessionHasEdits);
    }

    setSearching(value) {
                
        if (this._searching === value) {
            throw new Error(`Redundant state change: searching is already ${value}`);
        }
                
        const oldValue = this._searching;
        this._searching = Boolean(value);
                
        if (oldValue !== this._searching) {
            this._notifyListeners('searching', this._searching);
        }

        // Don't clear search query when exiting search mode
        // This preserves the search context for note creation
                
        return this;
    }

    get isSearching() {
        return this._searching;
    }

    get isIdle() {
        return !this._editing && !this._searching && !this._loading;
    }

    setActive(value) {
                
        const normalized = Boolean(value);
        if (this._active === normalized) {
            throw new Error(`Redundant state change: active is already ${normalized}`);
        }

        this._active = normalized;
        this._notifyListeners('active', this._active);
        return this;
    }

    get isActive() {
        return this._active;
    }

    setDirty(value) {
                
        if (this._dirty === value) {
            throw new Error(`Redundant state change: dirty is already ${value}`);
        }
                
        this._dirty = Boolean(value);
        this._notifyListeners('dirty', this._dirty);
        return this;
    }

    get isDirty() {
        return this._dirty;
    }

    setLoading(value) {
                
        if (this._loading === value) {
            throw new Error(`Redundant state change: loading is already ${value}`);
        }
        
        this._loading = Boolean(value);

        if (this._loading) {
            this._loadingStartedAt = performance.now();
            if (CONFIG.LOADING.SPINNER_DELAY > 0) {
                if (this._loadingTimeoutId) {
                    clearTimeout(this._loadingTimeoutId);
                    this._loadingTimeoutId = null;
                }

                this._loadingTimeoutId = setTimeout(() => {
                    document.body.classList.add(CONFIG.CLASSES.LOADING);
                    this._loadingTimeoutId = null;
                }, CONFIG.LOADING.SPINNER_DELAY);
            } else {
                document.body.classList.add(CONFIG.CLASSES.LOADING);
            }
        } else {
            document.body.classList.remove(CONFIG.CLASSES.LOADING);

            if (this._loadingTimeoutId) {
                clearTimeout(this._loadingTimeoutId);
                this._loadingTimeoutId = null;
            }

            if (this._loadingStartedAt === null) {
                throw new Error('setLoading(false) called without a prior setLoading(true)');
            }
            const durationMs = performance.now() - this._loadingStartedAt;
            this._loadingStartedAt = null;
        }

        if (CONFIG.LOADING.ARTIFICIAL_DELAY > 0) {
            if (this._loadingNotifyTimeoutId) {
                clearTimeout(this._loadingNotifyTimeoutId);
            }
            this._loadingNotifyTimeoutId = setTimeout(() => {
                this._loadingNotifyTimeoutId = null;
                this._notifyListeners('loading', this._loading);
            }, CONFIG.LOADING.ARTIFICIAL_DELAY);
        } else {
            this._notifyListeners('loading', this._loading);
        }

        return this;
    }

    get isLoading() {
        return this._loading;
    }

    setCurrentNoteId(noteId) {
                
        if (this._currentNoteId === noteId) {
            throw new Error(`Redundant state change: currentNoteId is already ${noteId}`);
        }
                
        this._currentNoteId = noteId;
        this._notifyListeners('currentNoteId', noteId);
        return this;
    }

    get currentNoteId() {
        return this._currentNoteId;
    }

    setHoveredNoteId(noteId) {
        const normalized = noteId || null;

        if (this._hoveredNoteId === normalized) {
            throw new Error(`Redundant state change: hoveredNoteId is already ${normalized}`);
        }

        this._hoveredNoteId = normalized;
        this._notifyListeners('hoveredNoteId', this._hoveredNoteId);
        return this;
    }

    get hoveredNoteId() {
        return this._hoveredNoteId;
    }

    markCaretHidden() {
        this._caretHidden = true;
        return this;
    }

    markCaretVisible() {
        this._caretHidden = false;
        return this;
    }

    get isCaretHidden() {
        return this._editing && this._caretHidden;
    }

    setLastSavedContent(content) {
        this._lastSavedContent = content;
        return this;
    }

    get lastSavedContent() {
        return this._lastSavedContent;
    }

    setCursorOffset(offset) {
        this._cursorOffset = offset;
        return this;
    }

    get cursorOffset() {
        return this._cursorOffset;
    }

    setCurrentContent(content) {
                
        if (this._currentContent === content) {
            throw new Error(`Redundant state change: currentContent is already set to the same value`);
        }
                
        this._currentContent = content;
        if (content === null) {
            this._lastSavedContent = null;
        }
        else {
            this._lastContentChangeTime = Date.now();
        }
        this._notifyListeners('currentContent', content);
        return this;
    }

    get currentContent() {
        return this._currentContent;
    }

    setKeyPressed(key, metaKey = false, shiftKey = false) {
        this._lastKeyPressed = key;
        this._metaKeyPressed = Boolean(metaKey);
        this._shiftKeyPressed = Boolean(shiftKey);
        return this;
    }

    get keyInfo() {
        return {
            key: this._lastKeyPressed,
            meta: this._metaKeyPressed,
            shift: this._shiftKeyPressed
        };
    }

    setClickTarget(target, coordinates = null) {
        this._lastClickTarget = target;
        if (coordinates) {
            this._coordinates = coordinates;
        }
        return this;
    }

    get clickTarget() {
        return this._lastClickTarget;
    }

    get coordinates() {
        return this._coordinates;
    }

    resetCoordinates() {
        this._coordinates = null;
        return this;
    }

    addListener(callback) {
        if (typeof callback === 'function') {
            this._listeners.push(callback);
        }
        return this;
    }

    removeListener(callback) {
        this._listeners = this._listeners.filter(listener => listener !== callback);
        return this;
    }

    _notifyListeners(property, newValue) {
                
        const oldValue = this[`_${property}`];

        Logger.logState(property, newValue, oldValue);
                
        this._listeners.forEach(listener => {
            try {
                listener(property, newValue);
            } catch (e) {
                Logger.logError('Error in listener callback', e);
            }
        });
    }

    getFullState() {
        const state = {
            modes: {
                editing: this._editing,
                searching: this._searching,
                loading: this._loading
            },
            context: {
                currentNoteId: this._currentNoteId,
                currentContent: this._currentContent,
                searchQuery: this._searchQuery
            },
            event: this._eventMemory
        };

        Logger.logFullState(state);
                
        return state;
    }

    validate() {
                
        if (this._editing && !this._currentNoteId) {
            const errorMsg = `Invariant violation: editing mode is active (${this._editing}) but no currentNoteId is set`;
            Logger.logError(errorMsg);
            throw new Error(errorMsg);
        }

        if (!this._editing && this._currentNoteId) {
            const errorMsg = `Invariant violation: editing mode is inactive (${this._editing}) but currentNoteId is set (${this._currentNoteId})`;
            Logger.logError(errorMsg);
            throw new Error(errorMsg);
        }
    }

    get lastContentChangeTime() {
        return this._lastContentChangeTime;
    }

    setClipboardNoteId(noteId) {
        
        if (noteId === null) {
            Logger.logAction('Clearing clipboard note ID');
            this._clipboardNoteId = null;
            this._notifyListeners('clipboardNoteId', null);
            return this;
        }

        if (this._clipboardNoteId === noteId) {
            throw new Error(`Redundant state change: clipboardNoteId is already ${noteId}`);
        }
        
        Logger.logAction(`Setting clipboard note ID to: ${noteId}`);
        this._clipboardNoteId = noteId;
        this._notifyListeners('clipboardNoteId', noteId);
        return this;
    }

    get clipboardNoteId() {
        return this._clipboardNoteId;
    }
    
    setClipboardMode(mode) {
        if (mode !== 'system' && mode !== 'note') {
            throw new Error(`Invalid clipboard mode: ${mode}. Must be 'system' or 'note'`);
        }
        
        if (this._clipboardMode === mode) {
            throw new Error(`Redundant state change: clipboardMode is already ${mode}`);
        }
        
        Logger.logAction(`Setting clipboard mode to: ${mode}`);
        this._clipboardMode = mode;
        return this;
    }
    
    get clipboardMode() {
        return this._clipboardMode;
    }

    setSearchQuery(query) {
        // Don't trigger redundancy check for search as it's expected to change frequently
        const oldQuery = this._searchQuery;
        this._searchQuery = query || '';
        
        if (oldQuery !== this._searchQuery) {
            this.resetRootTracking({ clear: true });
            // Update current tab's search query and save tab state
            const entry = this._ensureTabEntry(this._activeTabId);
            entry.searchQuery = this._searchQuery;
            this._notifyListeners('searchQuery', this._searchQuery);
            this._emitTabStateMutation('searchQuery');
        }
        
        return this;
    }

    get searchQuery() {
        return this._searchQuery;
    }

    // Infinite scroll helpers ------------------------------------------------

    _updateRootTracking(structure) {
        const knownRoots = this._getActiveKnownRoots();
        knownRoots.clear();
        const order = [];
        if (Array.isArray(structure)) {
            for (const entry of structure) {
                if (!entry || typeof entry !== 'object') {
                    continue;
                }
                const { id, parentId } = entry;
                if (typeof id !== 'string' || !id) {
                    continue;
                }
                if (parentId === null || parentId === undefined || parentId === '') {
                    knownRoots.add(id);
                    order.push(id);
                }
            }
        }
        this._tabRootOrder[this._activeTabId] = order;

        const currentTabId = this._activeTabId;
        const intersectedSeen = new Set();
        const seenRoots = this._getActiveSeenRoots();
        for (const rootId of seenRoots) {
            if (knownRoots.has(rootId)) {
                intersectedSeen.add(rootId);
            }
        }
        this._tabSeenRootIds[currentTabId] = intersectedSeen;

        queueMicrotask(async () => {
            const module = await import('./services/infinite-scroll-service.js');
            module.refreshOverlayMetrics();
        });
    }

    resetRootTracking(options = {}) {
        const shouldClear = options.clear !== false;
        if (shouldClear) {
            this._getActiveKnownRoots().clear();
            this._getActiveSeenRoots().clear();
        }
        queueMicrotask(async () => {
            const module = await import('./services/infinite-scroll-service.js');
            module.resetInfiniteScrollState();
        });
        return this;
    }

    _notifyInfiniteScrollTabSwitch() {
        queueMicrotask(async () => {
            const module = await import('./services/infinite-scroll-service.js');
            if (typeof module.handleTabSwitch === 'function') {
                module.handleTabSwitch();
                return;
            }
            module.resetInfiniteScrollState();
        });
    }

    markRootsAsSeen(rootIds) {
        if (!Array.isArray(rootIds)) {
            return false;
        }
        let changed = false;
        const knownRoots = this._getActiveKnownRoots();
        const seenRoots = this._getActiveSeenRoots();
        for (const id of rootIds) {
            if (typeof id !== 'string' || !knownRoots.has(id)) {
                continue;
            }
            const before = seenRoots.size;
            seenRoots.add(id);
            if (seenRoots.size !== before) {
                changed = true;
            }
        }
        return changed;
    }

    clearSeenRoots() {
        this._getActiveSeenRoots().clear();
        return this;
    }

    getUnseenRootCount() {
        const knownRoots = this._getActiveKnownRoots();
        const seenRoots = this._getActiveSeenRoots();
        return Math.max(0, knownRoots.size - seenRoots.size);
    }

    get seenRootCount() {
        return this._getActiveSeenRoots().size;
    }

    get knownRootCount() {
        return this._getActiveKnownRoots().size;
    }

    getSeenRootIds() {
        return Array.from(this._getActiveSeenRoots());
    }

    getLastKnownRootId() {
        const order = this._tabRootOrder[this._activeTabId] || [];
        if (!Array.isArray(order) || order.length === 0) {
            return null;
        }
        return order[order.length - 1];
    }

    isAnchorNearEnd(anchorId, distance = 3) {
        if (typeof anchorId !== 'string' || !anchorId) {
            return false;
        }
        const order = this._tabRootOrder[this._activeTabId] || [];
        const idx = order.indexOf(anchorId);
        if (idx === -1) return false;
        return (order.length - 1 - idx) <= distance;
    }

    setRootAnchorId(anchorId) {
        const tabId = this._activeTabId;
        if (typeof anchorId !== 'string' || !anchorId) {
            this._tabRootAnchors[tabId] = null;
            return this;
        }
        this._tabRootAnchors[tabId] = anchorId;
        return this;
    }

    getRootAnchorId() {
        return this._tabRootAnchors[this._activeTabId] || null;
    }


    // Tab management methods
    _ensureTabEntry(tabId) {
        if (!this._tabs[tabId]) {
            this._tabs[tabId] = { searchQuery: '', scrollY: 0, scrollAnchor: null };
        }
        this._ensureTabNoteHashes(tabId);
        return this._tabs[tabId];
    }

    _emitTabStateMutation(reason) {
        if (typeof this._tabStateUpdateHook === 'function') {
            this._tabStateUpdateHook({ reason, payload: this.getTabStatePayload() });
        }
    }

    get activeTabId() {
        return this._activeTabId;
    }

    get tabs() {
        return this._tabs;
    }

    setTabStateUpdateHook(callback) {
        if (callback && typeof callback !== 'function') {
            throw new Error('tab state update hook must be a function');
        }
        this._tabStateUpdateHook = callback;
        return this;
    }

    clearTabStateUpdateHook() {
        this._tabStateUpdateHook = null;
        return this;
    }

    setTabStateVersion(version) {
        if (typeof version !== 'number' || Number.isNaN(version)) {
            throw new Error('tab state version must be a number');
        }
        this._tabStateVersion = version;
        return this;
    }

    get tabStateVersion() {
        return this._tabStateVersion;
    }

    getTabStatePayload() {
        const tabs = {};
        const tabIds = Object.keys(this._tabs).sort();
        for (const tabId of tabIds) {
            const entry = this._tabs[tabId] || { searchQuery: '', scrollY: 0, anchorRootId: null, scrollAnchor: null };
            const scrollY = typeof entry.scrollY === 'number' && entry.scrollY >= 0 ? entry.scrollY : 0;
            tabs[tabId] = {
                searchQuery: typeof entry.searchQuery === 'string' ? entry.searchQuery : '',
                scrollY,
                anchorRootId: this._tabRootAnchors[tabId] || null,
                scrollAnchor: entry.scrollAnchor || null,
            };
        }
        return {
            activeTabId: this._activeTabId,
            tabs,
            version: this._tabStateVersion
        };
    }

    hydrateTabState(state, options = {}) {
        const emitUpdate = options.emitUpdate !== false;
        if (!state || typeof state !== 'object') {
            throw new Error('hydrateTabState requires a state object');
        }
        const { activeTabId, tabs } = state;
        if (!tabs || typeof tabs !== 'object' || Object.keys(tabs).length === 0) {
            throw new Error('hydrateTabState requires at least one tab');
        }
        const normalized = {};
        const tabIds = Object.keys(tabs);
        for (const tabId of tabIds) {
            const entry = tabs[tabId];
            if (!entry || typeof entry !== 'object') {
                throw new Error(`Invalid tab payload for tab ${tabId}`);
            }
            if (typeof entry.searchQuery !== 'string') {
                throw new Error(`Invalid searchQuery for tab ${tabId}`);
            }
            if (typeof entry.scrollY !== 'number' || entry.scrollY < 0) {
                throw new Error(`Invalid scrollY for tab ${tabId}`);
            }
            if (
                entry.anchorRootId !== null
                && entry.anchorRootId !== undefined
                && typeof entry.anchorRootId !== 'string'
            ) {
                throw new Error(`Invalid anchorRootId for tab ${tabId}`);
            }

            if (entry.scrollAnchor !== null && entry.scrollAnchor !== undefined && typeof entry.scrollAnchor !== 'object') {
                throw new Error(`Invalid scrollAnchor for tab ${tabId}`);
            }
            const searchQuery = entry.searchQuery;
            const scrollY = entry.scrollY;
            const anchorRootId = entry.anchorRootId || null;

            let scrollAnchor = null;
            if (entry.scrollAnchor && typeof entry.scrollAnchor === 'object') {
                const candidate = entry.scrollAnchor;
                if (typeof candidate.anchorId !== 'string' || candidate.anchorId.length === 0) {
                    throw new Error(`scrollAnchor.anchorId missing for tab ${tabId}`);
                }
                if (candidate.anchorBias !== 'center' && candidate.anchorBias !== 'top') {
                    throw new Error(`scrollAnchor.anchorBias invalid for tab ${tabId}`);
                }
                if (typeof candidate.intraOffset !== 'number' || candidate.intraOffset < 0) {
                    throw new Error(`scrollAnchor.intraOffset invalid for tab ${tabId}`);
                }
                if (!Array.isArray(candidate.beltPrev) || !Array.isArray(candidate.beltNext)) {
                    throw new Error(`scrollAnchor belt invalid for tab ${tabId}`);
                }
                if (!candidate.anchorSortKey || typeof candidate.anchorSortKey !== 'object') {
                    throw new Error(`scrollAnchor.anchorSortKey missing for tab ${tabId}`);
                }
                if (typeof candidate.anchorSortKey.domIndex !== 'number' || candidate.anchorSortKey.domIndex < 0) {
                    throw new Error(`scrollAnchor.anchorSortKey.domIndex invalid for tab ${tabId}`);
                }
                scrollAnchor = {
                    anchorId: candidate.anchorId,
                    anchorBias: candidate.anchorBias,
                    intraOffset: candidate.intraOffset,
                    beltPrev: candidate.beltPrev.filter(id => typeof id === 'string' && id.length > 0),
                    beltNext: candidate.beltNext.filter(id => typeof id === 'string' && id.length > 0),
                    anchorSortKey: { domIndex: candidate.anchorSortKey.domIndex },
                };
            }

            normalized[tabId] = { searchQuery, scrollY, anchorRootId, scrollAnchor };
            this._tabRootAnchors[tabId] = anchorRootId;
        }
        if (!normalized[activeTabId]) {
            throw new Error('Active tab missing from provided state');
        }
        const tabIdsList = Object.keys(normalized);
        const previousHashCaches = this._tabNoteHashes || Object.create(null);
        const nextHashCaches = Object.create(null);
        const previousKnownRoots = this._tabKnownRootIds || Object.create(null);
        const nextKnownRoots = Object.create(null);
        const previousSeenRoots = this._tabSeenRootIds || Object.create(null);
        const nextSeenRoots = Object.create(null);

        for (const tabId of tabIdsList) {
            nextHashCaches[tabId] = previousHashCaches[tabId] || new Map();
            nextKnownRoots[tabId] = previousKnownRoots[tabId] || new Set();
            nextSeenRoots[tabId] = previousSeenRoots[tabId] || new Set();
        }

        this._tabs = normalized;
        this._tabNoteHashes = nextHashCaches;
        this._tabKnownRootIds = nextKnownRoots;
        this._tabSeenRootIds = nextSeenRoots;
        this._activeTabId = activeTabId;
        this._ensureTabContainers(activeTabId);
        this._searchQuery = normalized[activeTabId].searchQuery;
        this.resetRootTracking({ clear: true });
        if (emitUpdate) {
            this._emitTabStateMutation('hydrate');
        }
        return this;
    }

    updateActiveTabScroll(scrollY) {
        return this.updateTabScroll(this._activeTabId, scrollY, true);
    }

    updateTabScroll(tabId, scrollY, emit = true) {
        if (typeof scrollY !== 'number' || scrollY < 0) {
            throw new Error('scrollY must be a non-negative number');
        }
        const entry = this._ensureTabEntry(tabId);
        if (entry.scrollY === scrollY) {
            return this;
        }
        entry.scrollY = scrollY;
        this._tabRootAnchors[tabId] = null;
        entry.scrollAnchor = null;
        if (emit) {
            this._emitTabStateMutation('scroll');
        }
        return this;
    }

    updateActiveTabScrollAnchor(scrollAnchor, emit = true) {
        return this.updateTabScrollAnchor(this._activeTabId, scrollAnchor, emit);
    }

    updateTabScrollAnchor(tabId, scrollAnchor, emit = true) {
        const entry = this._ensureTabEntry(tabId);
        if (scrollAnchor !== null && typeof scrollAnchor !== 'object') {
            throw new Error('scrollAnchor must be an object or null');
        }
        entry.scrollAnchor = scrollAnchor;
        if (emit) {
            this._emitTabStateMutation('scrollAnchor');
        }
        return this;
    }

    getTabScrollAnchor(tabId = null) {
        const targetTabId = tabId || this._activeTabId;
        const entry = this._tabs[targetTabId];
        return entry && entry.scrollAnchor ? entry.scrollAnchor : null;
    }

    beginIgnoreScrollEvents() {
        this._ignoreScrollEventsDepth += 1;
        return this;
    }

    endIgnoreScrollEvents() {
        if (this._ignoreScrollEventsDepth <= 0) {
            throw new Error('endIgnoreScrollEvents called without beginIgnoreScrollEvents');
        }
        this._ignoreScrollEventsDepth -= 1;
        return this;
    }

    shouldIgnoreScrollEvents() {
        return this._ignoreScrollEventsDepth > 0;
    }

    restoreScrollForActiveTab() {
        const tabId = this._activeTabId;
        const savedAnchor = this.getTabScrollAnchor(tabId);
        const savedScrollY = this.getTabScrollPosition(tabId);

        window.requestAnimationFrame(() => {
            this.beginIgnoreScrollEvents();
            try {
                restoreScrollFromAnchor(savedAnchor, { scrollYFallback: savedScrollY });
                const entry = this._ensureTabEntry(tabId);
                entry.scrollY = Math.max(0, Math.round(window.scrollY));
            } finally {
                this.endIgnoreScrollEvents();
            }
        });
    }

    switchToTab(tabId) {
        if (tabId < '0' || tabId > '9') {
            throw new Error(`Invalid tab ID: ${tabId}. Must be 0-9.`);
        }

        if (this._loading) {
            Logger.logNoop('Tab switch ignored while request is in-flight', {
                requestedTab: tabId,
                activeTab: this._activeTabId
            });
            return this;
        }

        // Save current scroll position to current tab
        const currentEntry = this._ensureTabEntry(this._activeTabId);
        currentEntry.scrollY = Math.max(0, Math.round(window.scrollY));
        currentEntry.searchQuery = this._searchQuery;

        // Switch to new tab
        const oldTabId = this._activeTabId;
        this._activeTabId = tabId;

        // Initialize tab if it doesn't exist
        const targetEntry = this._ensureTabEntry(tabId);

        // Update search query to match new tab
        const newQuery = targetEntry.searchQuery;
        console.log('Setting search query from tab', tabId, 'query:', newQuery);
        this._searchQuery = newQuery;
        this._notifyInfiniteScrollTabSwitch();

        // Notify listeners of changes
        if (oldTabId !== this._activeTabId) {
            this._notifyListeners('activeTab', this._activeTabId);
        }
        this._notifyListeners('searchQuery', this._searchQuery);
        this._emitTabStateMutation('switchTab');

        return this;
    }

    getTabScrollPosition(tabId = null) {
        const targetTabId = tabId || this._activeTabId;
        const entry = this._tabs[targetTabId];
        if (!entry || typeof entry.scrollY !== 'number' || entry.scrollY < 0) {
            return 0;
        }
        return entry.scrollY;
    }

    get isInitialPageLoad() {
        return this._isInitialPageLoad;
    }

    markInitialPageLoadComplete() {
        this._isInitialPageLoad = false;
        return this;
    }

    // Multi-device sync methods
    _generateClientId() {
        // Get or create a unique client ID for this browser tab
        let clientId = sessionStorage.getItem('metalist_client_id');
        if (!clientId) {
            clientId = crypto.randomUUID();
            sessionStorage.setItem('metalist_client_id', clientId);
        }
        return clientId;
    }

    get clientId() {
        return this._clientId;
    }

    setLastUpdateUUID(uuid) {
        this._lastUpdateUUID = uuid;
        return this;
    }

    get lastUpdateUUID() {
        return this._lastUpdateUUID;
    }
    
    // Connection state management
    setConnected(connected) {
        if (typeof connected !== 'boolean') {
            throw new Error('connected must be a boolean');
        }
        
        if (this._isConnected === connected) {
            throw new Error(`Redundant state change: isConnected is already ${connected}`);
        }
        
        Logger.logAction(`Connection state changed: ${connected ? 'connected' : 'disconnected'}`);
        this._isConnected = connected;
        this._notifyListeners('connectionState', connected);
        
        return this;
    }
    
    get isConnected() {
        return this._isConnected;
    }
    
    setConnectionErrorBannerVisible(visible) {
        if (typeof visible !== 'boolean') {
            throw new Error('visible must be a boolean');
        }
        
        if (this._connectionErrorBannerVisible === visible) {
            throw new Error(`Redundant state change: connectionErrorBannerVisible is already ${visible}`);
        }
        
        this._connectionErrorBannerVisible = visible;
        return this;
    }
    
    get connectionErrorBannerVisible() {
        return this._connectionErrorBannerVisible;
    }
    
    setUserActivity(active) {
        if (typeof active !== 'boolean') {
            throw new Error('active must be a boolean');
        }
        
        if (this._userActivity === active) {
            throw new Error(`Redundant state change: userActivity is already ${active}`);
        }
        
        this._userActivity = active;
        return this;
    }
    
    get userActivity() {
        return this._userActivity;
    }
}

export const ModeContextInstance = new ModeContext();
