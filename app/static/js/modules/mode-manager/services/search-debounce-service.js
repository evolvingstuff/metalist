let timeoutId = null;

export function cancelDebouncedSearchExecution() {
    if (timeoutId === null) {
        return;
    }
    clearTimeout(timeoutId);
    timeoutId = null;
}

export function scheduleDebouncedSearchExecution(delayMs, execute) {
    if (!Number.isInteger(delayMs) || delayMs < 0) {
        throw new Error('scheduleDebouncedSearchExecution requires non-negative integer delayMs');
    }
    if (typeof execute !== 'function') {
        throw new Error('scheduleDebouncedSearchExecution requires execute function');
    }

    cancelDebouncedSearchExecution();
    timeoutId = setTimeout(() => {
        timeoutId = null;
        execute();
    }, delayMs);
}

