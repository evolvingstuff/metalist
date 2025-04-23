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

class ModeContext {
  constructor() {
    // Core application modes
    this._editing = false;     // Whether user is editing a note
    this._searching = false;   // Whether search is active
    this._callingApi = false;  // Whether API calls are in progress
    this._active = true;       // Whether user is actively interacting with the app
    
    // Context properties
    this._currentNoteId = null;     // ID of currently active note
    this._lastSavedContent = null;  // Content last saved to server
    this._cursorOffset = null;      // Cursor position in current note
    this._searchQuery = null;       // Current search term
    
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
   * Set editing mode with validation
   * @param {boolean} value - New editing mode state
   * @returns {ModeContext} - For method chaining
   */
  setEditing(value) {
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
   * Set searching mode with validation
   * @param {boolean} value - New searching mode state
   * @returns {ModeContext} - For method chaining
   */
  setSearching(value) {
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
   * Set API calling mode with validation
   * @param {boolean} value - New API calling mode state
   * @returns {ModeContext} - For method chaining
   */
  setCallingApi(value) {
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
  
  //---------- CONTEXT SETTERS & GETTERS ----------//
  
  /**
   * Set current note ID
   * @param {string} noteId - ID of the current note
   * @returns {ModeContext} - For method chaining
   */
  setCurrentNoteId(noteId) {
    this._currentNoteId = noteId;
    this._notifyListeners('currentNoteId', this._currentNoteId);
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
    this._notifyListeners('searchQuery', this._searchQuery);
    return this;
  }
  
  /**
   * Get search query
   * @returns {string|null} Current search query or null
   */
  get searchQuery() {
    return this._searchQuery;
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
    this._listeners.forEach(listener => {
      try {
        listener(property, newValue);
      } catch (e) {
        console.error('+++ ModeManager ERROR: Error in listener callback', e);
      }
    });
  }
  
  /**
   * Get the complete state object for debugging
   * @returns {Object} Complete state object
   */
  getFullState() {
    return {
      modes: {
        editing: this._editing,
        searching: this._searching,
        callingApi: this._callingApi,
        idle: this.isIdle,
        active: this._active
      },
      context: {
        noteId: this._currentNoteId,
        searchQuery: this._searchQuery,
        cursorOffset: this._cursorOffset
      },
      eventMemory: {
        lastKey: this._lastKeyPressed,
        metaKey: this._metaKeyPressed,
        shiftKey: this._shiftKeyPressed
      }
    };
  }
}

// Create and export a singleton instance
export const ModeContextInstance = new ModeContext();