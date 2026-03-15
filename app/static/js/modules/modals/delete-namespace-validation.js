export const DELETE_NAMESPACE_CONFIRMATION_PHRASE = 'permanently delete';


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
        throw new Error(`Type '${DELETE_NAMESPACE_CONFIRMATION_PHRASE}' to confirm deletion`);
    }
    const normalizedConfirmationText = confirmationText.trim();
    if (normalizedConfirmationText !== DELETE_NAMESPACE_CONFIRMATION_PHRASE) {
        throw new Error(`Type '${DELETE_NAMESPACE_CONFIRMATION_PHRASE}' to confirm deletion`);
    }
    if (!hasPassword) {
        return {
            confirmation_text: normalizedConfirmationText,
        };
    }
    if (typeof currentPassword !== 'string' || currentPassword.length === 0) {
        throw new Error('Enter your current password');
    }
    return {
        confirmation_text: normalizedConfirmationText,
        current_password: currentPassword,
    };
}
