export function validateNamespaceDeletionSubmission({
    namespace,
    confirmationText,
    currentPassword,
    hasPassword,
    isCurrentNamespace,
    redirectNamespace,
}) {
    if (typeof namespace !== 'string' || namespace.trim().length === 0) {
        throw new Error('Current namespace is unavailable');
    }
    if (typeof hasPassword !== 'boolean') {
        throw new Error('Password state is unavailable');
    }
    if (typeof isCurrentNamespace !== 'boolean') {
        throw new Error('Current namespace state is unavailable');
    }
    if (typeof redirectNamespace !== 'string' || redirectNamespace.trim().length === 0) {
        throw new Error('Choose where to redirect after deletion');
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
            redirect_namespace: redirectNamespace.trim(),
        };
    }
    if (typeof currentPassword !== 'string' || currentPassword.length === 0) {
        throw new Error('Enter your current password');
    }
    return {
        confirmed_namespace: normalizedConfirmationText,
        current_password: currentPassword,
        redirect_namespace: redirectNamespace.trim(),
    };
}
