import assert from 'node:assert/strict';
import test from 'node:test';

import {
    shouldMarkExpandedEditSession,
    shouldPersistExpandedEditSession,
    shouldRestoreCollapsedStateLocally,
} from '../../app/static/js/modules/mode-manager/services/edit-session-collapse-policy-service.js';

test('repeated expansion in one edit session records persistence only once', () => {
    let expandedPersisted = false;
    let markedCount = 0;
    for (let count = 0; count < 2; count += 1) {
        const shouldMark = shouldMarkExpandedEditSession({
            isEditing: true,
            currentNoteId: 'note-1',
            targetNoteId: 'note-1',
            expandedPersisted,
        });
        if (shouldMark) {
            expandedPersisted = true;
            markedCount += 1;
        }
    }

    assert.equal(markedCount, 1);
    assert.equal(expandedPersisted, true);
});

test('expanding another note does not record the current edit session', () => {
    assert.equal(
        shouldMarkExpandedEditSession({
            isEditing: true,
            currentNoteId: 'note-1',
            targetNoteId: 'note-2',
            expandedPersisted: false,
        }),
        false,
    );
});

test('shouldPersistExpandedEditSession keeps only an edited, collapsed note expanded', () => {
    // Edited: stays expanded so the changes stay in view.
    assert.equal(shouldPersistExpandedEditSession({ startedCollapsed: true, hasEdits: true, expandedPersisted: false }), true);
    // Opened and left unchanged: collapses again.
    assert.equal(shouldPersistExpandedEditSession({ startedCollapsed: true, hasEdits: false, expandedPersisted: false }), false);
    // Not collapsed to begin with, or already saved as expanded.
    assert.equal(shouldPersistExpandedEditSession({ startedCollapsed: false, hasEdits: true, expandedPersisted: false }), false);
    assert.equal(shouldPersistExpandedEditSession({ startedCollapsed: true, hasEdits: true, expandedPersisted: true }), false);
});

test('shouldRestoreCollapsedStateLocally only restores for no-op sessions that started collapsed', () => {
    assert.equal(
        shouldRestoreCollapsedStateLocally({
            startedCollapsed: true,
            hasEdits: false,
            expandedPersisted: false,
        }),
        true,
    );

    assert.equal(
        shouldRestoreCollapsedStateLocally({
            startedCollapsed: false,
            hasEdits: false,
            expandedPersisted: false,
        }),
        false,
    );

    assert.equal(
        shouldRestoreCollapsedStateLocally({
            startedCollapsed: true,
            hasEdits: true,
            expandedPersisted: false,
        }),
        false,
    );

    assert.equal(
        shouldRestoreCollapsedStateLocally({
            startedCollapsed: true,
            hasEdits: false,
            expandedPersisted: true,
        }),
        false,
    );
});
