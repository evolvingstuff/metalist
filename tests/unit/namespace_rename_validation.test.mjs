import assert from 'node:assert/strict';
import test from 'node:test';

import { buildNamespaceRenamePayload } from '../../app/static/js/modules/modals/namespace-rename-validation.js';


test('buildNamespaceRenamePayload accepts a new non-overlapping name', () => {
    assert.deepEqual(
        buildNamespaceRenamePayload({
            currentNamespace: 'default',
            targetNamespace: 'personal',
            existingNamespaces: ['default', 'work'],
        }),
        { target_namespace: 'personal' },
    );
});


test('buildNamespaceRenamePayload rejects an existing namespace', () => {
    assert.throws(
        () => buildNamespaceRenamePayload({
            currentNamespace: 'default',
            targetNamespace: 'work',
            existingNamespaces: ['default', 'work'],
        }),
        /already exists/,
    );
});


test('buildNamespaceRenamePayload rejects invalid namespace syntax', () => {
    assert.throws(
        () => buildNamespaceRenamePayload({
            currentNamespace: 'default',
            targetNamespace: 'Personal Stuff',
            existingNamespaces: ['default'],
        }),
        /lowercase letters/,
    );
});
