export const LogCategory = {
    ACTION: 'ACTION',
    STATE: 'STATE',
    EVENT: 'EVENT',
    INIT: 'INIT',
    ERROR: 'ERROR',
    NOOP: 'NOOP',  
    DEBUG: 'DEBUG'  
};

export function logDebug(message, data = {}, category = LogCategory.EVENT, modes = null) {
    console.log(`[${category}]: ${message}`, {
        ...(modes && { modes }),
        ...data
    });
}

export function logAction(actionName, data = {}) {
    console.log(`[${LogCategory.ACTION}]: ${actionName}`, data);
}

export function logState(property, newValue, oldValue = undefined) {
    console.log(`[${LogCategory.STATE}]: ${property} changed`, {
        from: oldValue,
        to: newValue
    });
}

export function logFullState(stateObj) {
    console.log(`[${LogCategory.STATE}]: Current State:`, stateObj);
}

export function logInit(componentName) {
    console.log(`[${LogCategory.INIT}]: ${componentName} initialized`);
}

export function logError(message, error = {}) {
    console.error(`[${LogCategory.ERROR}]: ${message}`, error);
}

export function logNoop(message, data = {}) {
    console.log(`[${LogCategory.NOOP}]: ${message}`, data);
}