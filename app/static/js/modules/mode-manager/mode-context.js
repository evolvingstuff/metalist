import * as Logger from './mode-logger.js';

class ModeContext {
    constructor() {
                
        this._editing = false;     
        this._searching = false;   
        this._callingApi = false;  
        this._active = true;       
        this._dirty = false;       
        this._loading = false;     

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
    }

    setEditing(value) {
                
        if (this._editing === value) {
            throw new Error(`Redundant state change: editing is already ${value}`);
        }
                
        const oldValue = this._editing;
        this._editing = Boolean(value);
                
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

        if (!this._searching) {
            this._searchQuery = null;
        }
                
        return this;
    }

    get isSearching() {
        return this._searching;
    }

    setCallingApi(value) {
                
        if (this._callingApi === value) {
            throw new Error(`Redundant state change: callingApi is already ${value}`);
        }
                
        const oldValue = this._callingApi;
        this._callingApi = Boolean(value);
                
        if (oldValue !== this._callingApi) {
            this._notifyListeners('callingApi', this._callingApi);
        }
                
        return this;
    }

    get isCallingApi() {
        return this._callingApi;
    }

    get isIdle() {
        return !this._editing && !this._searching && !this._callingApi;
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
                
        this._loading = Boolean(value);
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
        // Check if we're setting to the same value (ABC pattern)
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
        // Check if we're setting to the same value (ABC pattern)
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
                callingApi: this._callingApi,
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
}

export const ModeContextInstance = new ModeContext();