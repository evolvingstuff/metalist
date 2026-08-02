const NAMESPACE_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;


export function buildNamespaceRenamePayload({
    currentNamespace,
    targetNamespace,
    existingNamespaces,
}) {
    if (typeof currentNamespace !== 'string' || currentNamespace.length === 0) {
        throw new Error('Current namespace is required');
    }
    if (typeof targetNamespace !== 'string') {
        throw new Error('New namespace name is required');
    }
    if (!Array.isArray(existingNamespaces)) {
        throw new Error('Existing namespaces are required');
    }
    const normalizedTarget = targetNamespace.trim();
    if (normalizedTarget.length === 0) {
        throw new Error('Enter a new namespace name');
    }
    if (!NAMESPACE_PATTERN.test(normalizedTarget)) {
        throw new Error("Namespace must contain only lowercase letters, digits, and '-'");
    }
    if (normalizedTarget === currentNamespace) {
        throw new Error('New namespace name must differ from the current name');
    }
    if (existingNamespaces.includes(normalizedTarget)) {
        throw new Error('That namespace already exists');
    }
    return { target_namespace: normalizedTarget };
}
