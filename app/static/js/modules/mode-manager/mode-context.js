import * as Logger from './mode-logger.js';
import { CONFIG } from '../config.js';

class ModeContext {
    constructor() {
                
        this._editing = false;     
        this._searching = false;
        this._active = true;       
        this._dirty = false;       
        this._loading = false;     
        this._loadingTimeoutId = null;

        this._currentNoteId = null;     
        this._lastSavedContent = null;  
        this._cursorOffset = null;      
        this._searchQuery = null;       
        this._currentContent = null;    

        this._lastKeyPressed = null;    
        this._lastClickTarget = null;   
        this._metaKeyPressed = false;   
        this._shiftKeyPressed = false;  

        this._listeners = [];
        this._savedCursorOffset = null;
        this._lastContentChangeTime = null;
        this._searchQuery = '';
        this._isInitialPageLoad = true;
        
        // Tab state management
        this._activeTabId = '0';
        this._tabs = {
            '0': { searchQuery: '', scrollY: 0 }
        };
        
        // Multi-device sync
        this._clientId = this._generateClientId();
        this._lastUpdateUUID = null;
        
        // Clipboard mode tracking
        this._clipboardMode = 'system'; // 'system' for text, 'note' for note copying
        
        // Editing heartbeat timer for dead client lock detection
        this._editingHeartbeatTimer = null;
        
        // Connection state tracking
        this._isConnected = true;
        this._connectionErrorBannerVisible = false;
    }

    setEditing(value) {
                
        if (this._editing === value) {
            throw new Error(`Redundant state change: editing is already ${value}`);
        }
                
        const oldValue = this._editing;
        this._editing = Boolean(value);
        
        // Manage editing heartbeat timer
        if (this._editing) {
            this._startEditingHeartbeat();
        } else {
            this._stopEditingHeartbeat();
        }
                
        if (oldValue !== this._editing) {
            this._notifyListeners('editing', this._editing);
        }
                
        return this;
    }

    get isEditing() {
        return this._editing;
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
        const oldValue = this._active;
        this._active = Boolean(value);
                
        if (oldValue !== this._active) {
            this._notifyListeners('active', this._active);
        }
                
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
        
        const oldValue = this._loading;
        this._loading = Boolean(value);

        if (this._loading) {
            
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

            if (CONFIG.LOADING.ARTIFICIAL_DELAY > 0) {
                return new Promise(resolve => {
                    setTimeout(() => {
                        resolve(this);
                    }, CONFIG.LOADING.ARTIFICIAL_DELAY);
                });
            }
        } else {
            
            document.body.classList.remove(CONFIG.CLASSES.LOADING);

            if (this._loadingTimeoutId) {
                clearTimeout(this._loadingTimeoutId);
                this._loadingTimeoutId = null;
            }
        }
        
        this._notifyListeners('loading', this._loading);
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

    setSavedCursorOffset(noteId, offset) {
        
        const currentValue = this._savedCursorOffset;
        if (currentValue && 
            currentValue.noteId === noteId && 
            currentValue.offset === offset) {
            throw new Error(`Redundant state change: savedCursorOffset is already set to the same values`);
        }
        
        this._savedCursorOffset = { noteId, offset };
        return this;
    }

    clearSavedCursorOffset() {
        
        if (this._savedCursorOffset === null) {
            throw new Error(`Redundant state change: savedCursorOffset is already null`);
        }
        
        this._savedCursorOffset = null;
        return this;
    }

    get savedCursorOffset() {
        return this._savedCursorOffset;
    }

    setSearchQuery(query) {
        this._searchQuery = query;
        this._notifyListeners('searchQuery', query);
        return this;
    }

    get searchQuery() {
        return this._searchQuery;
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
            // Update current tab's search query and save tab state
            if (this._tabs[this._activeTabId]) {
                this._tabs[this._activeTabId].searchQuery = this._searchQuery;
                this._saveTabStateToStorage();
            }
            
            // Also save to old localStorage key for backwards compatibility
            if (this._searchQuery) {
                localStorage.setItem('metalist_search_query', this._searchQuery);
            } else {
                localStorage.removeItem('metalist_search_query');
            }
            
            this._notifyListeners('searchQuery', this._searchQuery);
        }
        
        return this;
    }

    get searchQuery() {
        return this._searchQuery;
    }

    restoreSearchQueryFromStorage() {
        // Restore search query from localStorage without triggering notifications
        const savedQuery = localStorage.getItem('metalist_search_query');
        if (savedQuery) {
            this._searchQuery = savedQuery;
        }
        return this._searchQuery;
    }

    // Tab management methods
    get activeTabId() {
        return this._activeTabId;
    }

    get tabs() {
        return this._tabs;
    }

    switchToTab(tabId) {
        if (tabId < '0' || tabId > '9') {
            throw new Error(`Invalid tab ID: ${tabId}. Must be 0-9.`);
        }

        // Save current scroll position to current tab
        this._tabs[this._activeTabId] = this._tabs[this._activeTabId] || { searchQuery: '', scrollY: 0 };
        this._tabs[this._activeTabId].scrollY = window.scrollY;
        this._tabs[this._activeTabId].searchQuery = this._searchQuery;

        // Switch to new tab
        const oldTabId = this._activeTabId;
        this._activeTabId = tabId;

        // Initialize tab if it doesn't exist
        if (!this._tabs[tabId]) {
            console.log('Initializing new tab', tabId, 'with empty query');
            this._tabs[tabId] = { searchQuery: '', scrollY: 0 };
        }

        // Update search query to match new tab
        const newQuery = this._tabs[tabId].searchQuery;
        console.log('Setting search query from tab', tabId, 'query:', newQuery);
        this._searchQuery = newQuery;

        // Save tab state to localStorage
        this._saveTabStateToStorage();

        // Notify listeners of changes
        if (oldTabId !== this._activeTabId) {
            this._notifyListeners('activeTab', this._activeTabId);
        }
        this._notifyListeners('searchQuery', this._searchQuery);

        return this;
    }

    _saveTabStateToStorage() {
        const tabState = {
            activeTabId: this._activeTabId,
            tabs: this._tabs
        };
        localStorage.setItem('metalist_tab_state', JSON.stringify(tabState));
    }

    restoreTabStateFromStorage() {
        try {
            const savedState = localStorage.getItem('metalist_tab_state');
            if (savedState) {
                const tabState = JSON.parse(savedState);
                this._activeTabId = tabState.activeTabId || '0';
                this._tabs = tabState.tabs || { '0': { searchQuery: '', scrollY: 0 } };
                
                // Set search query to match active tab
                const activeTab = this._tabs[this._activeTabId];
                if (activeTab) {
                    this._searchQuery = activeTab.searchQuery || '';
                }
            }
        } catch (error) {
            console.warn('Failed to restore tab state from localStorage:', error);
            // Fall back to defaults
            this._activeTabId = '0';
            this._tabs = { '0': { searchQuery: '', scrollY: 0 } };
        }
        return this;
    }

    getTabScrollPosition(tabId = null) {
        const targetTabId = tabId || this._activeTabId;
        return this._tabs[targetTabId]?.scrollY || 0;
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
    
    // Editing heartbeat methods
    _startEditingHeartbeat() {
        // Clear any existing timer first
        this._stopEditingHeartbeat();
        
        // Send initial heartbeat immediately
        this._sendEditingHeartbeat();
        
        // Start periodic heartbeat every 1 second
        this._editingHeartbeatTimer = setInterval(() => {
            this._sendEditingHeartbeat();
        }, 1000);
        
        Logger.logDebug('Started editing heartbeat timer');
    }
    
    _stopEditingHeartbeat() {
        if (this._editingHeartbeatTimer) {
            clearInterval(this._editingHeartbeatTimer);
            this._editingHeartbeatTimer = null;
            Logger.logDebug('Stopped editing heartbeat timer');
        }
    }
    
    async _sendEditingHeartbeat() {
        if (!this._currentNoteId || !this._editing) {
            return;
        }
        
        try {
            const response = await fetch('/api/notes/acquire-lock', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    noteId: this._currentNoteId,
                    clientId: this._clientId,
                    lastUpdateUUID: this._lastUpdateUUID
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                this._lastUpdateUUID = data.updateUUID;
                Logger.logDebug('Editing heartbeat sent successfully');
            } else if (response.status === 409) {
                // Lock was taken by another client - exit edit mode
                Logger.logDebug('Lost edit lock to another client');
                this.setEditing(false);
                // TODO: Show user notification that they lost the lock
            }
        } catch (error) {
            Logger.logError('Failed to send editing heartbeat', error);
        }
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
}

export const ModeContextInstance = new ModeContext();