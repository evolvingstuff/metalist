import assert from 'node:assert/strict';
import test from 'node:test';

import {
    shouldPersistExpandedEditSession,
    shouldRestoreCollapsedStateLocally,
} from '../../app/static/js/modules/mode-manager/services/edit-session-collapse-policy-service.js';

test('shouldPersistExpandedEditSession only persists when a collapsed session has edits and is not yet persisted', () => {
    assert.equal(
        shouldPersistExpandedEditSession({
            startedCollapsed: true,
            hasEdits: true,
            expandedPersisted: false,
        }),
        true,
    );

    assert.equal(
        shouldPersistExpandedEditSession({
            startedCollapsed: false,
            hasEdits: true,
            expandedPersisted: false,
        }),
        false,
    );

    assert.equal(
        shouldPersistExpandedEditSession({
            startedCollapsed: true,
            hasEdits: false,
            expandedPersisted: false,
        }),
        false,
    );

    assert.equal(
        shouldPersistExpandedEditSession({
            startedCollapsed: true,
            hasEdits: true,
            expandedPersisted: true,
        }),
        false,
    );
});

test('shouldRestoreCollapsedStateLocally only restores for no-op sessions that started collapsed', () => {
    assert.equal(
        shouldRestoreCollapsedStateLocally({
            startedCollapsed: true,
            hasEdits: false,
        }),
        true,
    );

    assert.equal(
        shouldRestoreCollapsedStateLocally({
            startedCollapsed: false,
            hasEdits: false,
        }),
        false,
    );

    assert.equal(
        shouldRestoreCollapsedStateLocally({
            startedCollapsed: true,
            hasEdits: true,
        }),
        false,
    );
});
