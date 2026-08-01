export function selectNamespacePortsEditorProfile(entry) {
    if (!entry || typeof entry !== 'object') {
        throw new Error('Namespace entry missing');
    }
    const savedProfile = entry.saved_profile;
    if (savedProfile !== null) {
        if (!savedProfile || typeof savedProfile !== 'object') {
            throw new Error('Namespace entry saved_profile must be an object or null');
        }
        return savedProfile;
    }
    const defaultProfile = entry.default_profile;
    if (!defaultProfile || typeof defaultProfile !== 'object') {
        throw new Error('Namespace entry default_profile missing');
    }
    return defaultProfile;
}
