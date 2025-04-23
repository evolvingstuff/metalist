/*
    TODO:

    I want to move away from using a state machine. It is just too restricting,
    and there are all sorts of "hacks" needed to make it work, but then it is
    no longer purely a state machine.

    For instance, instead of having the states 'editing', 'searching', and 'idle'
    I would want this data:
    modeEditing: bool
    modeSearching: bool

    'idle' can be inferred from modeEditing = False && modeSearching = False

    In fact, there isn't really a need to specify 'idle' at all, it's just the
    absense of other modes.

    but one thing we would want to add in is modeCallingApi (or some name like that)
    to reflect when calls to the server are being made. This is an example of where
    the classic state machine model breaks down, because instead of transitioning from
    A to B, you are really doing some stuff in between, and so you have to add memory
    to know what state to transition to upon getting a response from the server.

    I want the ModeManager object to contain all the vars that are currently in
    state-context.js (with some changes, like I just described). I want those vars
    to start with underscores, and use getters and setters for everything so
    we can add in state validation.

    I want all event handling done inside of this object. This will be more "imperative"
    in nature, but frankly, things are getting to abstract and non-local to reason about
    and it gets tougher and tougher to make even simple changes in the state machine
    paradigm.


 */

/**
 * ModeManager
 * 
 * A new approach to application state management that replaces the traditional state machine model.
 * 
 * ## Motivation
 * 
 * The traditional state machine model has limitations:
 * - States are mutually exclusive, while real app behavior often requires overlapping states
 * - Complex transitions make the code harder to reason about and maintain
 * - Adding new states requires complex transition logic
 * - Async operations (like API calls) don't fit well in the state machine paradigm
 * 
 * ## Design Principles
 * 
 * 1. Mode-based instead of state-based:
 *    - Multiple modes can be active simultaneously (e.g., editing + API calling)
 *    - "Idle" is simply the absence of active modes, not a special state
 * 
 * 2. Imperative event handling:
 *    - Event handlers update state directly rather than requesting transitions
 *    - More straightforward code flow makes it easier to reason about
 * 
 * 3. Private state with validation:
 *    - Internal state variables are private (leading underscore)
 *    - Getters/setters provide validation and derived properties
 *    - Consistent state is enforced through validation
 * 
 * ## Implementation Strategy
 * 
 * This implementation will run in parallel with the existing state machine during migration:
 * - Event listeners are registered BEFORE existing state machine
 * - Initially, the ModeManager only tracks state but doesn't control application behavior
 * - Console logging shows state changes for debugging
 * - Gradual migration by moving control from state machine to ModeManager
 * 
 * ## Usage Example
 * 
 * ```javascript
 * // Initialize
 * const modeManager = new ModeManager();
 * 
 * // Check current mode
 * if (modeManager.isEditing) {
 *   // Handle editing-specific logic
 * }
 * 
 * // Multiple modes can be active
 * if (modeManager.isEditing && modeManager.isCallingApi) {
 *   // Handle special case when both editing and API call are happening
 * }
 * 
 * // Derived "idle" state
 * if (modeManager.isIdle) {
 *   // Handle idle case
 * }
 * ```
 */
export class ModeManager {
  /**
   * Create a new ModeManager instance
   */
  constructor() {
    // Core application modes (private properties)
    this._editing = false;     // Whether user is editing a note
    this._searching = false;   // Whether search is active
    this._callingApi = false;  // Whether API calls are in progress
    
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
    
    // Debug flag
    this._debugEnabled = true;
    
    console.log('[ModeManager] Instantiated');
    
    // Register event listeners
    this._registerEventListeners();
  }
  
  /**
   * Register event listeners (must happen BEFORE StateMachine listeners)
   * Initially just observe and log, don't interfere with existing behavior
   * @private
   */
  _registerEventListeners() {
    // Track click events but don't handle them
    document.addEventListener('click', this._handleClick.bind(this), { capture: true });
    
    // Track keydown events
    document.addEventListener('keydown', this._handleKeyDown.bind(this), { capture: true });
    
    // Track input events
    document.addEventListener('input', this._handleInput.bind(this), { capture: true });
    
    // Track search-related events
    document.addEventListener('focusin', this._handleFocus.bind(this), { capture: true });
    document.addEventListener('focusout', this._handleBlur.bind(this), { capture: true });
    
    this._logDebug('Event listeners registered');
  }
  
  /**
   * Handle click events
   * @param {Event} event - DOM click event
   * @private
   */
  _handleClick(event) {
    this._lastClickTarget = event.target;
    
    // Analyze the click target
    const noteContent = event.target.closest('.note-content');
    const searchField = event.target.closest('#search-input');
    const createButton = event.target.closest('#create-note-button');
    
    // Update modes based on what was clicked
    if (noteContent) {
      this._setEditing(true);
      this._setSearching(false);
      this._currentNoteId = noteContent.dataset.noteId || null;
      this._logDebug('Click in note content detected', { noteId: this._currentNoteId });
    } else if (searchField) {
      this._setSearching(true);
      this._logDebug('Click in search field detected');
    } else if (createButton) {
      this._logDebug('Create note button clicked');
    }
    
    // Don't stop propagation - let event continue to state machine
  }
  
  /**
   * Handle keyboard events
   * @param {KeyboardEvent} event - DOM keydown event
   * @private
   */
  _handleKeyDown(event) {
    this._lastKeyPressed = event.key;
    this._metaKeyPressed = event.metaKey || event.ctrlKey;
    this._shiftKeyPressed = event.shiftKey;
    
    this._logDebug('Key pressed', { 
      key: event.key, 
      meta: this._metaKeyPressed, 
      shift: this._shiftKeyPressed 
    });
    
    // Special key handling for mode changes
    if (event.key === 'Escape') {
      if (this._searching) {
        this._setSearching(false);
        this._logDebug('Search cancelled via Escape key');
      }
    }
    
    // Handle meta+/ for search
    if (this._metaKeyPressed && event.key === '/') {
      this._setSearching(true);
      this._logDebug('Search activated via meta+/');
    }
    
    // Handle other key combinations...
  }
  
  /**
   * Handle input events
   * @param {Event} event - DOM input event
   * @private
   */
  _handleInput(event) {
    const noteContent = event.target.closest('.note-content');
    const searchField = event.target.closest('#search-input');
    
    if (noteContent) {
      this._setEditing(true);
      this._logDebug('Note content changed');
    } else if (searchField) {
      this._searchQuery = searchField.value;
      this._setSearching(true);
      this._logDebug('Search query changed', { query: this._searchQuery });
    }
  }
  
  /**
   * Handle focus events
   * @param {FocusEvent} event - DOM focusin event
   * @private
   */
  _handleFocus(event) {
    const searchField = event.target.closest('#search-input');
    
    if (searchField) {
      this._setSearching(true);
      this._logDebug('Search field focused');
    }
  }
  
  /**
   * Handle blur events
   * @param {FocusEvent} event - DOM focusout event
   * @private
   */
  _handleBlur(event) {
    const searchField = event.target.closest('#search-input');
    
    if (searchField) {
      if (!this._searchQuery) {
        this._setSearching(false);
        this._logDebug('Search field blurred and empty - exiting search mode');
      }
    }
  }
  
  /**
   * Log debug information if debug is enabled
   * @param {string} message - Debug message
   * @param {Object} data - Optional data to log
   * @private
   */
  _logDebug(message, data = {}) {
    if (this._debugEnabled) {
      console.log(`[ModeManager] ${message}`, {
        modes: {
          editing: this._editing,
          searching: this._searching,
          callingApi: this._callingApi,
          idle: this.isIdle
        },
        ...data
      });
    }
  }
  
  /**
   * Set editing mode with validation
   * @param {boolean} value - New editing mode state
   * @private
   */
  _setEditing(value) {
    this._editing = Boolean(value);
    
    // Additional logic could be added here later
    // For example: synchronizing UI, validating state combinations
  }
  
  /**
   * Set searching mode with validation
   * @param {boolean} value - New searching mode state
   * @private
   */
  _setSearching(value) {
    this._searching = Boolean(value);
    
    // If search is turned off, clear search query
    if (!value) {
      this._searchQuery = null;
    }
  }
  
  /**
   * Set API calling mode with validation
   * @param {boolean} value - New API calling mode state
   * @private
   */
  _setCallingApi(value) {
    this._callingApi = Boolean(value);
    
    // Additional validation could be added here
  }
  
  // PUBLIC GETTERS
  
  /**
   * Check if editing mode is active
   * @returns {boolean} True if editing
   */
  get isEditing() {
    return this._editing;
  }
  
  /**
   * Check if searching mode is active
   * @returns {boolean} True if searching
   */
  get isSearching() {
    return this._searching;
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
   * Get current note ID
   * @returns {string|null} Current note ID or null
   */
  get currentNoteId() {
    return this._currentNoteId;
  }
  
  /**
   * Get current search query
   * @returns {string|null} Current search query or null
   */
  get searchQuery() {
    return this._searchQuery;
  }
  
  /**
   * Toggle debug logging on/off
   * @param {boolean} enabled - Whether debug logging should be enabled
   * @returns {ModeManager} This instance for chaining
   */
  setDebug(enabled) {
    this._debugEnabled = Boolean(enabled);
    this._logDebug(`Debug mode ${this._debugEnabled ? 'enabled' : 'disabled'}`);
    return this;
  }
  
  /**
   * Print current mode state to console
   * Useful for debugging
   * @returns {ModeManager} This instance for chaining
   */
  debugState() {
    console.log('[ModeManager] Current State:', {
      modes: {
        editing: this._editing,
        searching: this._searching,
        callingApi: this._callingApi,
        idle: this.isIdle
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
    });
    return this;
  }
}