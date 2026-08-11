export function classifyApiFailure(error, response) {
    if (typeof response === 'undefined') {
        throw new Error('classifyApiFailure requires response (use null)');
    }

    if (response !== null) {
        if (typeof response !== 'object') {
            throw new Error('classifyApiFailure response must be an object or null');
        }
        if (!Number.isInteger(response.status)) {
            throw new Error('classifyApiFailure response.status must be an integer');
        }
        if (response.status === 401) {
            return {
                kind: 'auth',
                message: 'Your session has expired. Please log in again.',
            };
        }
        if (response.status >= 500) {
            return {
                kind: 'http',
                message: `Server error (${response.status}). Please try again.`,
            };
        }
        if (response.status >= 400) {
            return {
                kind: 'http',
                message: `Request failed (${response.status}). Please check your input and try again.`,
            };
        }
        return {
            kind: 'http',
            message: `Unexpected error (${response.status}). Please try again.`,
        };
    }

    if (!error || typeof error !== 'object') {
        throw new Error('classifyApiFailure requires error object when response is null');
    }
    if (typeof error.name !== 'string') {
        throw new Error('classifyApiFailure requires error.name string');
    }
    if (typeof error.message !== 'string') {
        throw new Error('classifyApiFailure requires error.message string');
    }

    if (error.name === 'AbortError') {
        return {
            kind: 'network',
            message: 'Request timed out. Please try again.',
        };
    }
    if (error.name === 'TypeError' && (
        error.message.includes('fetch')
        || error.message.includes('Network request failed')
        || error.message.includes('Failed to fetch')
        || error.message.includes('Load failed')
    )) {
        return {
            kind: 'network',
            message: 'Cannot reach server. Please check your internet connection.',
        };
    }
    return {
        kind: 'internal',
        error,
    };
}
