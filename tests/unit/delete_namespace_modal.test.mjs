import assert from 'node:assert/strict';
import test from 'node:test';

import {
    extractDeletableNamespaceNames,
    validateNamespaceDeletionSubmission,
} from '../../app/static/js/modules/modals/delete-namespace-validation.js';


test('extractDeletableNamespaceNames builds the server-provided selection list', () => {
    const names = extractDeletableNamespaceNames({
        namespaces: [
            { namespace: 'default' },
            { namespace: 'cla' },
            { namespace: 'thomas' },
        ],
    });

    assert.deepEqual(names, ['default', 'cla', 'thomas']);
});


test('extractDeletableNamespaceNames rejects malformed catalog entries', () => {
    assert.throws(
        () => extractDeletableNamespaceNames({ namespaces: [{ namespace: '' }] }),
        /namespace name/,
    );
});


test('validateNamespaceDeletionSubmission requires the exact namespace name', () => {
    assert.throws(
        () => validateNamespaceDeletionSubmission({
            namespace: 'work',
            confirmationText: 'delete',
            currentPassword: '',
            hasPassword: false,
            isCurrentNamespace: true,
            redirectNamespace: 'default',
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
            isCurrentNamespace: true,
            redirectNamespace: 'default',
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
        isCurrentNamespace: true,
        redirectNamespace: 'cla',
    });

    assert.deepEqual(payload, {
        confirmed_namespace: 'work',
        current_password: 'abcd',
        redirect_namespace: 'cla',
    });
});


test('validateNamespaceDeletionSubmission allows deleting default', () => {
    const payload = validateNamespaceDeletionSubmission({
        namespace: 'default',
        confirmationText: 'default',
        currentPassword: '',
        hasPassword: false,
        isCurrentNamespace: true,
        redirectNamespace: 'default',
    });

    assert.deepEqual(payload, {
        confirmed_namespace: 'default',
        redirect_namespace: 'default',
    });
});


test('validateNamespaceDeletionSubmission requires an active-namespace redirect', () => {
    assert.throws(
        () => validateNamespaceDeletionSubmission({
            namespace: 'work',
            confirmationText: 'work',
            currentPassword: '',
            hasPassword: false,
            isCurrentNamespace: true,
            redirectNamespace: '',
        }),
        /Choose where to redirect/,
    );
});
