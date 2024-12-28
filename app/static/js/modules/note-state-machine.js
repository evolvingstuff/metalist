import { CONFIG } from './config.js';

/**
 * IMPORTANT ASSUMPTIONS AND GOTCHAS:
 * 
 * 1. State Transitions:
 *    - Valid transitions are strictly defined in this.transitions
 *    - When in 'editing' state, transition to 'searching' must save content first
 *    - Edit state is never preserved during search
 *    - All transitions from 'editing' must ensure content is saved
 *    - NEVER use 'finishing' state for search transitions - go directly to 'searching'
 * 
 * 2. State Data:
 *    - searchQuery persists only during search state
 *    - lastSavedContent must be updated before leaving 'editing'
 *    - currentNote reference is cleared if exiting edit mode
 * 
 * 3. Async Operations:
 *    - Content saves must complete before state changes
 *    - Search operations shouldn't interrupt pending saves
 *    - State might change during async operations
 * 
 * 4. Search Specific:
 *    - Search can be triggered from any state
 *    - If in edit mode, save changes before searching
 *    - From search, valid transitions are to either 'idle' or 'editing'
 *    - ALWAYS use NoteState.startSearch() for entering search mode
 */

/**
 * State machine for managing note editing and searching states
 */
export const NoteStateMachine = {
    /**
     * Possible states for note interactions
     */
    states: {
        IDLE: 'idle',         // Not editing or searching
        EDITING: 'editing',    // Actively editing a note
        FINISHING: 'finishing',  // Add finishing state
        SEARCHING: 'searching' // Actively searching notes
    },

    /**
     * Valid state transitions
     */
    transitions: {
        idle: ['editing', 'searching'],
        editing: ['idle', 'finishing', 'searching'],  // Allow transition to finishing
        finishing: ['idle'],  // Finishing can only go back to idle
        searching: ['idle', 'editing']
    },

    /**
     * Current state
     */
    currentState: 'idle',

    /**
     * Debug history
     */
    debugHistory: [],
    maxHistoryLength: 100,

    /**
     * State-specific data
     */
    stateData: {
        currentNote: null,     // Current note being edited
        searchQuery: '',       // Current search query
        lastSavedContent: null,// Last saved content of current note
        cursorPosition: null   // Current cursor position in note
    },

    /**
     * State change listeners
     */
    listeners: [],

    /**
     * Initialize the state machine
     */
    init() {
        this.currentState = 'idle';
        this.stateData = {
            currentNote: null,
            searchQuery: '',
            lastSavedContent: null,
            cursorPosition: null
        };
        this.listeners = [];
        this.debugHistory = [];
        
        if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
            this.addListener((from, to, data) => {
                console.log(`State transition: ${from} → ${to}`, data);
            });
        }
    },

    /**
     * Add a state change listener
     * @param {Function} listener - Called with (fromState, toState, stateData)
     */
    addListener(listener) {
        this.listeners.push(listener);
    },

    /**
     * Remove a state change listener
     * @param {Function} listener - Listener to remove
     */
    removeListener(listener) {
        this.listeners = this.listeners.filter(l => l !== listener);
    },

    /**
     * Attempt to transition to a new state
     * @param {string} to - State to transition to
     * @param {Function} action - Action to perform during transition
     * @param {Object} data - Additional data for the state
     * @returns {Promise<boolean>} - Whether transition was successful
     */
    async transition(to, action, data = {}) {
        const from = this.currentState;
        
        // Skip if trying to transition to current state
        if (from === to) {
            if (CONFIG.DEBUG.LOG_STATE_MACHINE) {
                console.log(`Already in state: ${to}`);
            }
            return true;
        }

        if (!this.transitions[from]?.includes(to)) {
            console.error(`Invalid state transition attempted: ${from} → ${to}`, data);
            return false;
        }

        this.currentState = to;
        this.stateData = { ...this.stateData, ...data };
        
        // Notify listeners
        this.listeners.forEach(listener => listener(from, to, this.stateData));
        
        return true;
    },

    /**
     * Add entry to debug history
     * @param {Object} entry - Debug history entry
     */
    addToDebugHistory(entry) {
        this.debugHistory.push(entry);
        if (this.debugHistory.length > this.maxHistoryLength) {
            this.debugHistory.shift();
        }
    },

    /**
     * Get debug history
     * @returns {Array} Copy of debug history
     */
    getDebugHistory() {
        return [...this.debugHistory];
    },

    /**
     * Clear debug history
     */
    clearDebugHistory() {
        this.debugHistory = [];
    },

    /**
     * Get current state information
     * @returns {Object} Current state and data
     */
    getState() {
        return {
            state: this.currentState,
            data: { ...this.stateData }  // Return copy to prevent direct modification
        };
    },

    /**
     * Check if a transition is valid
     * @param {string} toState - State to check transition to
     * @returns {boolean} Whether transition is valid
     */
    canTransitionTo(toState) {
        const validTransitions = this.transitions[this.currentState];
        return validTransitions?.includes(toState) ?? false;
    },

    /**
     * Reset state machine to idle
     */
    reset() {
        this.init();
    }
}; 