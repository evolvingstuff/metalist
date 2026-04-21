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
