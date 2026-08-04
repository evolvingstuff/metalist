const DEFAULT_NAMESPACE = 'default';


export function buildLoginTitle(namespace) {
    if (typeof namespace !== 'string') {
        throw new Error('buildLoginTitle requires namespace string');
    }
    const trimmedNamespace = namespace.trim();
    if (trimmedNamespace.length === 0 || trimmedNamespace === DEFAULT_NAMESPACE) {
        return 'MetaList';
    }
    return `MetaList [${trimmedNamespace}]`;
}


export function parseLoginNamespaceCatalog(payload) {
    if (!payload || typeof payload !== 'object') {
        throw new Error('Login namespace catalog must be an object');
    }

    const currentNamespace = payload.current_namespace;
    if (typeof currentNamespace !== 'string' || currentNamespace.trim().length === 0) {
        throw new Error('Login namespace catalog missing current_namespace');
    }

    const rawNamespaces = payload.namespaces;
    if (!Array.isArray(rawNamespaces)) {
        throw new Error('Login namespace catalog missing namespaces');
    }

    const namespaces = [];
    const seenNamespaces = new Set();
    for (const entry of rawNamespaces) {
        if (typeof entry !== 'string' || entry.trim().length === 0) {
            throw new Error('Login namespace catalog namespaces must be non-empty strings');
        }
        if (seenNamespaces.has(entry)) {
            throw new Error(`Login namespace catalog duplicate namespace ${entry}`);
        }
        seenNamespaces.add(entry);
        namespaces.push(entry);
    }

    if (!seenNamespaces.has(currentNamespace)) {
        throw new Error(`Login namespace catalog missing current namespace ${currentNamespace}`);
    }

    return {
        currentNamespace,
        namespaces,
    };
}


export function buildLoginNamespaceOpeningCopy(namespace) {
    if (typeof namespace !== 'string') {
        throw new Error('buildLoginNamespaceOpeningCopy requires namespace string');
    }
    const trimmedNamespace = namespace.trim();
    if (trimmedNamespace.length === 0) {
        throw new Error('buildLoginNamespaceOpeningCopy requires non-empty namespace');
    }
    return {
        subtitle: `Opening ${trimmedNamespace}…`,
        loadingTitle: 'Switching namespace…',
        loadingMessage: `Connecting to ${trimmedNamespace} on its configured port…`,
        statusText: `Opening ${trimmedNamespace}…`,
    };
}


export function rewriteNamespaceUrlPreservingCurrentHost(rawUrl, currentLocation) {
    if (typeof rawUrl !== 'string' || rawUrl.length === 0) {
        throw new Error('rewriteNamespaceUrlPreservingCurrentHost requires rawUrl string');
    }
    if (!currentLocation || typeof currentLocation !== 'object') {
        throw new Error('rewriteNamespaceUrlPreservingCurrentHost requires currentLocation object');
    }

    const hostname = currentLocation.hostname;
    if (typeof hostname !== 'string' || hostname.length === 0) {
        throw new Error('rewriteNamespaceUrlPreservingCurrentHost requires currentLocation.hostname');
    }

    const parsedUrl = new URL(rawUrl);
    parsedUrl.hostname = hostname;
    return parsedUrl.toString();
}


export function openPendingNamespaceTab(browserWindow) {
    if (!browserWindow || typeof browserWindow !== 'object') {
        throw new Error('openPendingNamespaceTab requires browserWindow object');
    }
    if (typeof browserWindow.open !== 'function') {
        throw new Error('openPendingNamespaceTab requires window.open');
    }
    const pendingTab = browserWindow.open('about:blank', '_blank');
    if (!pendingTab || typeof pendingTab !== 'object') {
        throw new Error('Browser blocked the namespace tab');
    }
    pendingTab.opener = null;
    return pendingTab;
}


export function navigateNamespaceInNewTab(rawUrl, browserWindow, pendingTab) {
    if (!browserWindow || typeof browserWindow !== 'object') {
        throw new Error('navigateNamespaceInNewTab requires browserWindow object');
    }
    if (!pendingTab || typeof pendingTab !== 'object' || pendingTab.closed) {
        throw new Error('Namespace tab was closed before it could open');
    }
    if (!pendingTab.location || typeof pendingTab.location.replace !== 'function') {
        throw new Error('navigateNamespaceInNewTab requires pending tab location.replace');
    }
    const navigationUrl = rewriteNamespaceUrlPreservingCurrentHost(rawUrl, browserWindow.location);
    pendingTab.location.replace(navigationUrl);
}
