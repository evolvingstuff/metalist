/**
 * Pure description of a Yes/No confirmation question from the server (kept free
 * of DOM and network imports so it can be unit tested).
 */

export const CONFIRMATION_QUESTION_KIND = 'change_confirmation';

/** The validated question, or a loud error for a malformed server event. */
export function describeConfirmationQuestion(event) {
    if (typeof event !== 'object' || event === null || event.type !== 'bulk_question') {
        throw new TypeError('Confirmation requires a bulk_question event');
    }
    if (event.kind !== CONFIRMATION_QUESTION_KIND) {
        throw new Error(`Not a confirmation question: ${event.kind}`);
    }
    if (typeof event.question_id !== 'string' || event.question_id === '') {
        throw new Error('Confirmation question requires question_id');
    }
    if (typeof event.label !== 'string' || event.label.trim() === '') {
        throw new Error('Confirmation question requires a label');
    }
    return { questionId: event.question_id, label: event.label };
}
