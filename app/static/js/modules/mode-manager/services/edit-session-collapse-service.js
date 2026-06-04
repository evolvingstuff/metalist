import { NotesAPI } from '../../api-client.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';
import { setNoteCollapsedLocally } from './collapse-affordance-service.js';
import {
    shouldPersistExpandedEditSession,
    shouldRestoreCollapsedStateLocally,
} from './edit-session-collapse-policy-service.js';

export async function persistExpandedEditSessionIfNeeded(noteId) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('persistExpandedEditSessionIfNeeded requires noteId');
    }

    const shouldPersist = shouldPersistExpandedEditSession({
        startedCollapsed: ModeContext.editSessionStartedCollapsed,
        hasEdits: ModeContext.editSessionHasEdits,
        expandedPersisted: ModeContext.editSessionExpandedPersisted,
    });
    if (!shouldPersist) {
        return false;
    }

    await NotesAPI.expandNote(noteId);
    ModeContext.markEditSessionExpandedPersisted();
    return true;
}

export function restoreCollapsedStateLocallyIfNeeded(noteElement) {
    if (!(noteElement instanceof HTMLElement)) {
        throw new Error('restoreCollapsedStateLocallyIfNeeded requires note element');
    }

    const shouldRestore = shouldRestoreCollapsedStateLocally({
        startedCollapsed: ModeContext.editSessionStartedCollapsed,
        hasEdits: ModeContext.editSessionHasEdits,
        expandedPersisted: ModeContext.editSessionExpandedPersisted,
    });
    if (!shouldRestore) {
        return false;
    }

    setNoteCollapsedLocally(noteElement, true);
    return true;
}

export function initializeEditSessionCollapseStateFromNoteElement(noteElement) {
    if (!(noteElement instanceof HTMLElement)) {
        throw new Error('initializeEditSessionCollapseStateFromNoteElement requires note element');
    }
    if (ModeContext.editSessionStartedCollapsed || ModeContext.editSessionHasEdits || ModeContext.editSessionExpandedPersisted) {
        return false;
    }

    const startedCollapsed = noteElement.dataset.isCollapsed === 'true';
    if (!startedCollapsed) {
        return false;
    }

    ModeContext.resetEditSessionState({ startedCollapsed: true });
    return true;
}

export {
    shouldPersistExpandedEditSession,
    shouldRestoreCollapsedStateLocally,
} from './edit-session-collapse-policy-service.js';
