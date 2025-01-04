export const idleTransitions = {
    enter: async (data, prevState) => {
        // Clean slate when entering idle
        return {};
    },

    exit: async (data, nextState) => {
        // No cleanup needed
        return {};
    }
}; 