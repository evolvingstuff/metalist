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
     * Execute a state transition with an optional command
     */
    async execute(fromState, toState, data = {}, command = null) {
        // Validate transition
        if (!this.validTransitions[fromState]?.includes(toState)) {
            throw new Error(`Invalid transition: ${fromState} -> ${toState}`);
        }

        try {
            // 1. Exit handler
            console.log(' [COORDINATOR] Running exit handler', { fromState, toState });
            const exitData = await this.handlers[fromState].exit?.(data, toState) || {};
            console.log(' [COORDINATOR] Exit handler complete');

            // 2. Execute command if provided
            let commandData = {};
            if (command) {
                console.log(' [COORDINATOR] Executing command');
                commandData = await command(exitData) || {};
                console.log(' [COORDINATOR] Command complete');
            }

            // 3. Enter handler
            console.log(' [COORDINATOR] Running enter handler');
            const enterData = await this.handlers[toState].enter?.({
                ...data,
                ...exitData,
                ...commandData
            }, fromState) || {};
            console.log(' [COORDINATOR] Enter handler complete');

            // Merge and return new state data
            return {
                ...exitData,
                ...commandData,
                ...enterData
            };
        } catch (error) {
            console.error(' [COORDINATOR] Transition failed:', error);
            throw new Error(`Transition failed: ${error.message}`);
        }
    }
}; 