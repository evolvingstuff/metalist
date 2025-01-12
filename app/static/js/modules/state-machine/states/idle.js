/**
 * Idle State
 * 
 * Default application state when no active interactions.
 * Serves as the base state for transitions to editing/searching.
 * 
 * State Data:
 * - No persistent data
 * 
 * Transitions:
 * - Enter: Cleans up any leftover state
 * - Exit: No specific cleanup needed
 * 
 * @example
 * // Return to idle state
 * await transition('idle');
 */

export const idleTransitions = {
    enter: async (data, prevState) => {
        // Clean slate when entering idle
        return {};
    },

    exit: async (data, nextState) => {
        // No cleanup needed
        return {};
    },

    handleEvent: (event) => {
        switch (event.type) {
            case 'CLICK_OUTSIDE_NOTE':
                return null;
            default:
                return null;
        }
    }
}; 