function requireBooleanResult(value, name) {
    if (typeof value !== 'boolean') {
        throw new Error(`${name} must return a boolean`);
    }
    return value;
}


export async function waitForCommandAvailability(options) {
    if (!options || typeof options !== 'object' || Array.isArray(options)) {
        throw new Error('waitForCommandAvailability requires an options object');
    }
    const {
        isBusy,
        isLoading,
        timeoutMs,
        pollIntervalMs,
    } = options;
    if (typeof isBusy !== 'function') {
        throw new Error('waitForCommandAvailability requires isBusy');
    }
    if (typeof isLoading !== 'function') {
        throw new Error('waitForCommandAvailability requires isLoading');
    }
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
        throw new Error('waitForCommandAvailability requires positive timeoutMs');
    }
    if (!Number.isFinite(pollIntervalMs) || pollIntervalMs <= 0) {
        throw new Error('waitForCommandAvailability requires positive pollIntervalMs');
    }

    const startedAt = performance.now();
    while (true) {
        const busy = requireBooleanResult(isBusy(), 'isBusy');
        const loading = requireBooleanResult(isLoading(), 'isLoading');
        if (!busy && !loading) {
            return;
        }
        const elapsedMs = performance.now() - startedAt;
        if (elapsedMs >= timeoutMs) {
            throw new Error(
                `Timed out waiting to start backup after ${Math.round(elapsedMs)} ms`
            );
        }
        await new Promise((resolve) => {
            setTimeout(resolve, pollIntervalMs);
        });
    }
}
