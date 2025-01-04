import { editingTransitions } from './states/editing.js';
import { searchingTransitions } from './states/searching.js';
import { idleTransitions } from './states/idle.js';

/**
 * State Transition Coordinator
 * 
 * Manages state transitions and their associated enter/exit hooks.
 * Validates transitions and coordinates state cleanup/setup.
 * 
 * Features:
 * - Validates allowed state transitions
 * - Executes exit hooks for old state
 * - Executes enter hooks for new state
 * - Manages transition data flow
 * - Handles transition errors
 * 
 * @example
 * // Execute transition
 * await StateTransitions.execute('idle', 'editing', {
 *   nextNote: noteElement
 * });
 */
export const StateTransitions = {
    // Define valid state transitions
    validTransitions: {
        idle: ['editing', 'searching'],
        editing: ['idle', 'editing', 'searching'],
        searching: ['idle', 'editing']
    },

    // State handlers
    handlers: {
        idle: idleTransitions,
        editing: editingTransitions,
        searching: searchingTransitions
    },

    /**
     * Execute a state transition
     */
    async execute(fromState, toState, data = {}) {
        // Validate transition
        if (!this.validTransitions[fromState]?.includes(toState)) {
            throw new Error(`Invalid transition: ${fromState} -> ${toState}`);
        }

        try {
            // Run exit handler for current state
            const exitData = await this.handlers[fromState].exit?.(data, toState) || {};

            // Run enter handler for new state
            const enterData = await this.handlers[toState].enter?.(data, fromState) || {};

            // Merge and return new state data
            return {
                ...exitData,
                ...enterData
            };
        } catch (error) {
            console.error('Transition failed:', error);
            throw error;
        }
    }
}; 