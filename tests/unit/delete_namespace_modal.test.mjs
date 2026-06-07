import assert from 'node:assert/strict';
import test from 'node:test';

import {
    validateNamespaceDeletionSubmission,
} from '../../app/static/js/modules/modals/delete-namespace-validation.js';


test('validateNamespaceDeletionSubmission requires the exact namespace name', () => {
    assert.throws(
        () => validateNamespaceDeletionSubmission({
            namespace: 'work',
            confirmationText: 'delete',
            currentPassword: '',
            hasPassword: false,
        }),
        /Type 'work'/,
    );
});


test('validateNamespaceDeletionSubmission requires current password when password protection is enabled', () => {
    assert.throws(
        () => validateNamespaceDeletionSubmission({
            namespace: 'work',
            confirmationText: 'work',
            currentPassword: '',
            hasPassword: true,
        }),
        /Enter your current password/,
    );
});


test('validateNamespaceDeletionSubmission returns normalized payload', () => {
    const payload = validateNamespaceDeletionSubmission({
        namespace: 'work',
        confirmationText: ' work ',
        currentPassword: 'abcd',
        hasPassword: true,
    });

    assert.deepEqual(payload, {
        confirmed_namespace: 'work',
        current_password: 'abcd',
    });
});
