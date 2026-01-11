export const LogCategory = {
    ACTION: 'ACTION',
    STATE: 'STATE',
    EVENT: 'EVENT',
    INIT: 'INIT',
    ERROR: 'ERROR',
    NOOP: 'NOOP',  
    DEBUG: 'DEBUG'  
};

export function logDebug(message, data, category, modes) {
    if (typeof category === 'undefined') {
        category = LogCategory.EVENT;
    }
    if (typeof data === 'undefined' || data === null) {
        data = {};
    }
    if (typeof modes === 'undefined') {
        modes = null;
    }

    console.log(`[${category}]: ${message}`, {
        ...(modes && { modes }),
        ...data
    });
}

export function logAction(actionName, data) {
    if (typeof data === 'undefined' || data === null) {
        data = {};
    }
    console.log(`[${LogCategory.ACTION}]: ${actionName}`, data);
}

export function logState(property, newValue, oldValue) {
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

export function logError(message, error) {
    if (typeof error === 'undefined' || error === null) {
        error = {};
    }
    console.error(`[${LogCategory.ERROR}]: ${message}`, error);
}

export function logNoop(message, data) {
    if (typeof data === 'undefined' || data === null) {
        data = {};
    }
    console.log(`[${LogCategory.NOOP}]: ${message}`, data);
}
