import { CONFIG } from './config.js';

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
        SAVING: 'saving',      // In the process of saving changes
        FINISHING: 'finishing',// Cleaning up after editing
        SEARCHING: 'searching' // Actively searching notes
    },

    /**
     * Valid state transitions
     */
    transitions: {
        idle: ['editing', 'searching'],
        editing: ['saving', 'finishing', 'searching'],
        saving: ['editing', 'finishing', 'searching'],
        finishing: ['idle', 'searching'],
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
     * @param {string} newState - State to transition to
     * @param {Function} action - Action to perform during transition
     * @param {Object} data - Additional data for the state
     * @returns {Promise<boolean>} - Whether transition was successful
     */
    async transition(newState, action, data = {}) {
        const validTransitions = this.transitions[this.currentState];
        
        if (!validTransitions?.includes(newState)) {
            console.warn(
                `Invalid state transition attempted:`,
                `${this.currentState} → ${newState}`,
                data
            );
            return false;
        }

        const oldState = this.currentState;
        const timestamp = new Date();
        const transitionId = crypto.randomUUID();
        
        try {
            // Update state data
            this.stateData = {
                ...this.stateData,
                ...data
            };
            
            // Perform state change
            this.currentState = newState;
            
            // Add debug entry for transition start
            if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
                this.addToDebugHistory({
                    id: transitionId,
                    timestamp,
                    type: 'transition-start',
                    from: oldState,
                    to: newState,
                    data: { ...this.stateData },
                    stack: new Error().stack
                });
            }
            
            // Notify listeners
            this.listeners.forEach(listener => {
                listener(oldState, newState, this.stateData);
            });
            
            // Execute action if provided
            if (action) {
                await action(this.stateData);
            }

            // Add debug entry for transition complete
            if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
                this.addToDebugHistory({
                    id: transitionId,
                    timestamp: new Date(),
                    type: 'transition-complete',
                    from: oldState,
                    to: newState,
                    data: { ...this.stateData }
                });
            }
            
            return true;
        } catch (error) {
            // Add debug entry for transition error
            if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
                this.addToDebugHistory({
                    id: transitionId,
                    timestamp: new Date(),
                    type: 'transition-error',
                    from: oldState,
                    to: newState,
                    error: error.message,
                    stack: error.stack
                });
            }

            // Revert state on error
            this.currentState = oldState;
            console.error('Error during state transition:', error);
            return false;
        }
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