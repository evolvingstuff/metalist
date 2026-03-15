import assert from 'node:assert/strict';
import test from 'node:test';

import {
    DELETE_NAMESPACE_CONFIRMATION_PHRASE,
    validateNamespaceDeletionSubmission,
} from '../../app/static/js/modules/modals/delete-namespace-validation.js';


test('validateNamespaceDeletionSubmission requires the exact confirmation phrase', () => {
    assert.throws(
        () => validateNamespaceDeletionSubmission({
            namespace: 'work',
            confirmationText: 'delete',
            currentPassword: '',
            hasPassword: false,
        }),
        new RegExp(`Type '${DELETE_NAMESPACE_CONFIRMATION_PHRASE}'`),
    );
});


test('validateNamespaceDeletionSubmission requires current password when password protection is enabled', () => {
    assert.throws(
        () => validateNamespaceDeletionSubmission({
            namespace: 'work',
            confirmationText: DELETE_NAMESPACE_CONFIRMATION_PHRASE,
            currentPassword: '',
            hasPassword: true,
        }),
        /Enter your current password/,
    );
});


test('validateNamespaceDeletionSubmission returns normalized payload', () => {
    const payload = validateNamespaceDeletionSubmission({
        namespace: 'work',
        confirmationText: ` ${DELETE_NAMESPACE_CONFIRMATION_PHRASE} `,
        currentPassword: 'abcd',
        hasPassword: true,
    });

    assert.deepEqual(payload, {
        confirmation_text: DELETE_NAMESPACE_CONFIRMATION_PHRASE,
        current_password: 'abcd',
    });
});
