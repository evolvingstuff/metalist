export function getRequiredTabId() {
    const tabId = sessionStorage.getItem('metalist_tab_id');
    if (typeof tabId !== 'string' || tabId.length === 0) {
        throw new Error('metalist_tab_id missing from sessionStorage');
    }
    return tabId;
}


export function buildSessionHeaders(includeContentType) {
    if (typeof includeContentType !== 'boolean') {
        throw new Error('buildSessionHeaders requires boolean includeContentType');
    }

    const headers = {
        'X-Metalist-Tab-Id': getRequiredTabId(),
    };
    if (includeContentType) {
        headers['Content-Type'] = 'application/json';
    }
    return headers;
}
