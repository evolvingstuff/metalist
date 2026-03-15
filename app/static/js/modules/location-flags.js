export function consumeBooleanQueryFlag({ location, history, flagName }) {
    if (!location || typeof location.href !== 'string' || location.href.length === 0) {
        throw new Error('consumeBooleanQueryFlag requires location.href');
    }
    if (!history || typeof history.replaceState !== 'function') {
        throw new Error('consumeBooleanQueryFlag requires history.replaceState');
    }
    if (typeof flagName !== 'string' || flagName.length === 0) {
        throw new Error('consumeBooleanQueryFlag requires flagName');
    }

    const url = new URL(location.href);
    if (url.searchParams.get(flagName) !== '1') {
        return false;
    }

    url.searchParams.delete(flagName);
    const nextQuery = url.searchParams.toString();
    const nextUrl = `${url.pathname}${nextQuery === '' ? '' : `?${nextQuery}`}${url.hash}`;
    history.replaceState({}, '', nextUrl);
    return true;
}
