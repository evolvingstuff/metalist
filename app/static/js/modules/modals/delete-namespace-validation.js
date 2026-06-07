export function validateNamespaceDeletionSubmission({
    namespace,
    confirmationText,
    currentPassword,
    hasPassword,
}) {
    if (typeof namespace !== 'string' || namespace.trim().length === 0) {
        throw new Error('Current namespace is unavailable');
    }
    if (namespace === 'default') {
        throw new Error('Default namespace cannot be deleted');
    }
    if (typeof hasPassword !== 'boolean') {
        throw new Error('Password state is unavailable');
    }
    if (typeof confirmationText !== 'string') {
        throw new Error(`Type '${namespace}' to confirm deletion`);
    }
    const normalizedConfirmationText = confirmationText.trim();
    if (normalizedConfirmationText !== namespace) {
        throw new Error(`Type '${namespace}' to confirm deletion`);
    }
    if (!hasPassword) {
        return {
            confirmed_namespace: normalizedConfirmationText,
        };
    }
    if (typeof currentPassword !== 'string' || currentPassword.length === 0) {
        throw new Error('Enter your current password');
    }
    return {
        confirmed_namespace: normalizedConfirmationText,
        current_password: currentPassword,
    };
}
