/**
 * ModeContext
 * 
 * Stores and manages the mode state of the application.
 * Replaces the complex state machine context with a simpler, more flexible approach.
 * 
 * Contains:
 * - Core mode flags (editing, searching, callingApi)
 * - Context data (noteId, cursor position, etc.)
 * - Event information (key pressed, click coordinates, etc.)
 */

import * as Logger from './mode-logger.js';

class ModeContext {
  constructor() {
    // Core application modes
    this._editing = false;     // Whether user is editing a note
    this._searching = false;   // Whether search is active
    this._callingApi = false;  // Whether API calls are in progress
    this._active = true;       // Whether user is actively interacting with the app
    this._dirty = false;       // Whether content has unsaved changes
    this._loading = false;     // Whether content is loading
    
    // Context properties
    this._currentNoteId = null;     // ID of currently active note
    this._lastSavedContent = null;  // Content last saved to server
    this._cursorOffset = null;      // Cursor position in current note
    this._searchQuery = null;       // Current search term
    this._currentContent = null;    // Current content being edited
    
    // Event memory
    this._lastKeyPressed = null;    // Last keyboard key pressed
    this._lastClickTarget = null;   // Last element clicked
    this._metaKeyPressed = false;   // Meta/Ctrl key state
    this._shiftKeyPressed = false;  // Shift key state
    
    // Store listeners for state changes
    this._listeners = [];
  }
  
  //---------- MODE SETTERS & GETTERS ----------//
  
  /**
   * Set editing mode on/off
   * @param {boolean} value - Whether editing mode is active
   * @returns {ModeContext} - For method chaining
   */
  setEditing(value) {
    // Redundancy check - fail fast on programming errors
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
  
  /**
   * Check if editing mode is active
   * @returns {boolean} True if editing
   */
  get isEditing() {
    return this._editing;
  }
  
  /**
   * Set searching mode on/off
   * @param {boolean} value - Whether search mode is active
   * @returns {ModeContext} - For method chaining
   */
  setSearching(value) {
    // Redundancy check - fail fast on programming errors
    if (this._searching === value) {
      throw new Error(`Redundant state change: searching is already ${value}`);
    }
    
    const oldValue = this._searching;
    this._searching = Boolean(value);
    
    if (oldValue !== this._searching) {
      this._notifyListeners('searching', this._searching);
    }
    
    // If search is turned off, clear search query
    if (!this._searching) {
      this._searchQuery = null;
    }
    
    return this;
  }
  
  /**
   * Check if searching mode is active
   * @returns {boolean} True if searching
   */
  get isSearching() {
    return this._searching;
  }
  
  /**
   * Set API call flag on/off
   * @param {boolean} value - Whether API call is in progress
   * @returns {ModeContext} - For method chaining
   */
  setCallingApi(value) {
    // Redundancy check - fail fast on programming errors
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
  
  /**
   * Check if API call is in progress
   * @returns {boolean} True if calling API
   */
  get isCallingApi() {
    return this._callingApi;
  }
  
  /**
   * Check if all modes are inactive (idle state)
   * @returns {boolean} True if no modes are active
   */
  get isIdle() {
    return !this._editing && !this._searching && !this._callingApi;
  }
  
  /**
   * Set user active state
   * @param {boolean} value - Whether user is active
   * @returns {ModeContext} - For method chaining
   */
  setActive(value) {
    const oldValue = this._active;
    this._active = Boolean(value);
    
    if (oldValue !== this._active) {
      this._notifyListeners('active', this._active);
    }
    
    return this;
  }
  
  /**
   * Check if user is actively interacting with the app
   * @returns {boolean} True if user is active
   */
  get isActive() {
    return this._active;
  }
  
  /**
   * Set dirty flag
   * @param {boolean} value - Whether content has unsaved changes
   * @returns {ModeContext} - For method chaining
   */
  setDirty(value) {
    // Redundancy check - fail fast on programming errors
    if (this._dirty === value) {
      throw new Error(`Redundant state change: dirty is already ${value}`);
    }
    
    this._dirty = Boolean(value);
    this._notifyListeners('dirty', this._dirty);
    return this;
  }
  
  /**
   * Check if content has unsaved changes
   * @returns {boolean} True if dirty
   */
  get isDirty() {
    return this._dirty;
  }
  
  /**
   * Set loading flag on/off
   * @param {boolean} value - Whether loading is in progress
   * @returns {ModeContext} - For method chaining
   */
  setLoading(value) {
    // Redundancy check - fail fast on programming errors
    if (this._loading === value) {
      throw new Error(`Redundant state change: loading is already ${value}`);
    }
    
    this._loading = Boolean(value);
    this._notifyListeners('loading', this._loading);
    return this;
  }
  
  /**
   * Check if content is loading
   * @returns {boolean} True if loading
   */
  get isLoading() {
    return this._loading;
  }
  
  //---------- CONTEXT SETTERS & GETTERS ----------//
  
  /**
   * Set current note ID
   * @param {string|null} noteId - ID of the current note, or null if no note selected
   * @returns {ModeContext} - For method chaining
   */
  setCurrentNoteId(noteId) {
    // Redundancy check - fail fast on programming errors
    if (this._currentNoteId === noteId) {
      throw new Error(`Redundant state change: currentNoteId is already ${noteId}`);
    }
    
    this._currentNoteId = noteId;
    this._notifyListeners('currentNoteId', noteId);
    return this;
  }
  
  /**
   * Get current note ID
   * @returns {string|null} Current note ID or null
   */
  get currentNoteId() {
    return this._currentNoteId;
  }
  
  /**
   * Set last saved content
   * @param {string} content - The content last saved
   * @returns {ModeContext} - For method chaining
   */
  setLastSavedContent(content) {
    this._lastSavedContent = content;
    return this;
  }
  
  /**
   * Get last saved content
   * @returns {string|null} Last saved content or null
   */
  get lastSavedContent() {
    return this._lastSavedContent;
  }
  
  /**
   * Set cursor offset in current note
   * @param {number} offset - Character offset from start of note
   * @returns {ModeContext} - For method chaining
   */
  setCursorOffset(offset) {
    this._cursorOffset = offset;
    return this;
  }
  
  /**
   * Get cursor offset
   * @returns {number|null} Cursor offset or null
   */
  get cursorOffset() {
    return this._cursorOffset;
  }
  
  /**
   * Set search query
   * @param {string} query - Search query text
   * @returns {ModeContext} - For method chaining
   */
  setSearchQuery(query) {
    this._searchQuery = query;
    this._notifyListeners('searchQuery', query);
    return this;
  }
  
  /**
   * Get search query
   * @returns {string|null} Current search query or null
   */
  get searchQuery() {
    return this._searchQuery;
  }
  
  /**
   * Set current content being edited
   * @param {string} content - Content text
   * @returns {ModeContext} - For method chaining
   */
  setCurrentContent(content) {
    // Redundancy check - fail fast on programming errors
    if (this._currentContent === content) {
      throw new Error(`Redundant state change: currentContent is already set to the same value`);
    }
    
    this._currentContent = content;
    this._notifyListeners('currentContent', content);
    return this;
  }
  
  /**
   * Get current content being edited
   * @returns {string|null} Current content or null if not editing
   */
  get currentContent() {
    return this._currentContent;
  }
  
  //---------- EVENT MEMORY ----------//
  
  /**
   * Set the last key pressed
   * @param {string} key - Key that was pressed
   * @param {boolean} metaKey - Whether meta/ctrl was pressed
   * @param {boolean} shiftKey - Whether shift was pressed
   * @returns {ModeContext} - For method chaining
   */
  setKeyPressed(key, metaKey = false, shiftKey = false) {
    this._lastKeyPressed = key;
    this._metaKeyPressed = Boolean(metaKey);
    this._shiftKeyPressed = Boolean(shiftKey);
    return this;
  }
  
  /**
   * Get last key pressed
   * @returns {Object} Key information object
   */
  get keyInfo() {
    return {
      key: this._lastKeyPressed,
      meta: this._metaKeyPressed,
      shift: this._shiftKeyPressed
    };
  }
  
  /**
   * Set last click target element
   * @param {Element} target - DOM element that was clicked
   * @param {Object} coordinates - Click coordinates {x, y}
   * @returns {ModeContext} - For method chaining
   */
  setClickTarget(target, coordinates = null) {
    this._lastClickTarget = target;
    if (coordinates) {
      this._coordinates = coordinates;
    }
    return this;
  }
  
  /**
   * Get last click target
   * @returns {Element|null} Last clicked DOM element or null
   */
  get clickTarget() {
    return this._lastClickTarget;
  }
  
  /**
   * Get click coordinates
   * @returns {Object|null} Click coordinates {x, y} or null
   */
  get coordinates() {
    return this._coordinates;
  }
  
  //---------- STATE LISTENERS ----------//
  
  /**
   * Add a listener for mode changes
   * @param {Function} callback - Called when mode changes with (property, newValue)
   * @returns {ModeContext} - For method chaining
   */
  addListener(callback) {
    if (typeof callback === 'function') {
      this._listeners.push(callback);
    }
    return this;
  }
  
  /**
   * Remove a listener
   * @param {Function} callback - The callback to remove
   * @returns {ModeContext} - For method chaining
   */
  removeListener(callback) {
    this._listeners = this._listeners.filter(listener => listener !== callback);
    return this;
  }
  
  /**
   * Notify listeners of a property change
   * @param {string} property - Name of the property that changed
   * @param {any} newValue - New value of the property
   * @private
   */
  _notifyListeners(property, newValue) {
    // Store old value before it's changed
    const oldValue = this[`_${property}`];
    
    // Log the state change with proper categorization
    Logger.logState(property, newValue, oldValue);
    
    this._listeners.forEach(listener => {
      try {
        listener(property, newValue);
      } catch (e) {
        Logger.logError('Error in listener callback', e);
      }
    });
  }
  
  /**
   * Get the complete state object for debugging
   * @returns {Object} Complete state object
   */
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
    
    // Log the full state with the new categorized logger
    Logger.logFullState(state);
    
    return state;
  }
  
  /**
   * Validate state invariants to ensure system consistency
   * Throws an error if any invariants are violated
   */
  validate() {
    // Invariant 1: If editing, must have a currentNoteId
    if (this._editing && !this._currentNoteId) {
      const errorMsg = `Invariant violation: editing mode is active (${this._editing}) but no currentNoteId is set`;
      Logger.logError(errorMsg);
      throw new Error(errorMsg);
    }
    
    // Invariant 2: If not editing, must not have a currentNoteId
    if (!this._editing && this._currentNoteId) {
      const errorMsg = `Invariant violation: editing mode is inactive (${this._editing}) but currentNoteId is set (${this._currentNoteId})`;
      Logger.logError(errorMsg);
      throw new Error(errorMsg);
    }
    
    // Invariant 3: If searching, must have a non-empty search query (or we are in the process of beginning a search)
    // Commented out as it might be too restrictive - search might start without query initially
    // if (this._searching && !this._searchQuery) {
    //   const errorMsg = `Invariant violation: searching mode is active but no search query is set`;
    //   Logger.logError(errorMsg);
    //   throw new Error(errorMsg);
    // }
  }
}

// Create and export a singleton instance
export const ModeContextInstance = new ModeContext();