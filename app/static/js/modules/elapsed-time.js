export function formatElapsedDuration(elapsedMilliseconds) {
    if (
        typeof elapsedMilliseconds !== 'number'
        || !Number.isFinite(elapsedMilliseconds)
        || elapsedMilliseconds < 0
    ) {
        throw new Error('elapsedMilliseconds must be a non-negative finite number');
    }

    const totalSeconds = Math.floor(elapsedMilliseconds / 1000);
    if (totalSeconds < 60) {
        return `${totalSeconds}s`;
    }

    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}m ${seconds}s`;
}
