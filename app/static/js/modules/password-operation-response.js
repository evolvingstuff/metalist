export async function readPasswordOperationResponse(response) {
    if (
        !response
        || typeof response.ok !== 'boolean'
        || !Number.isInteger(response.status)
        || typeof response.json !== 'function'
    ) {
        throw new TypeError('Password operation response is invalid');
    }

    const payload = await response.json().catch(() => {
        throw new Error(
            `Password request failed with HTTP ${response.status} and returned invalid JSON`,
        );
    });

    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new Error(`Password request returned invalid JSON with HTTP ${response.status}`);
    }
    if (!response.ok) {
        if (typeof payload.detail === 'string' && payload.detail !== '') {
            throw new Error(payload.detail);
        }
        throw new Error(`Password request failed with HTTP ${response.status}`);
    }
    return payload;
}
