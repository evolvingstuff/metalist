export async function settleResult(callback) {
    if (typeof callback !== 'function') {
        throw new Error('settleResult requires callback function');
    }
    return Promise.resolve()
        .then(callback)
        .then(
            (value) => ({ ok: true, value }),
            (error) => ({ ok: false, error }),
        );
}
