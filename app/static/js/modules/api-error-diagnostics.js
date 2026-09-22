const ERROR_TYPE = /^[A-Za-z_][A-Za-z0-9_]*$/;
const CODE_LOCATION = /^(?:app(?:\/[A-Za-z_][A-Za-z0-9_]*)+\.py:\d+|external)$/;

export async function describeApiFailure(response) {
    const base = `API call failed: ${response.status} ${response.statusText}`;
    if (response.status < 500 || !response.headers.get('content-type')?.includes('application/json')) {
        return base;
    }

    const body = await response.json();
    const diagnostic = body?.diagnostic;
    if (!ERROR_TYPE.test(diagnostic?.errorType) || !CODE_LOCATION.test(diagnostic?.codeLocation)) {
        return base;
    }
    return `${base} (${diagnostic.errorType} at ${diagnostic.codeLocation})`;
}
