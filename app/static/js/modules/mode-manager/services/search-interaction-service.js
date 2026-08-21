import { NotesAPI } from '../../api-client.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';

const stateByTabId = Object.create(null);

function getActiveTabId() {
    const tabId = ModeContext.activeTabId;
    if (typeof tabId !== 'string' || tabId.length === 0) {
        throw new Error('ModeContext.activeTabId must be a non-empty string');
    }
    return tabId;
}

function getExecutedQuery() {
    const query = ModeContext.getExecutedSearchQuery();
    if (typeof query !== 'string') {
        throw new Error('ModeContext.getExecutedSearchQuery() must return a string');
    }
    return query;
}

export function primeActiveSearchInteractionState() {
    const tabId = getActiveTabId();
    const query = getExecutedQuery();
    if (!Object.prototype.hasOwnProperty.call(stateByTabId, tabId)) {
        stateByTabId[tabId] = { query, engagedNoteId: null, pendingNoteId: null };
        return;
    }
    const state = stateByTabId[tabId];
    if (state.query !== query) {
        stateByTabId[tabId] = { query, engagedNoteId: null, pendingNoteId: null };
    }
}

export async function recordNoteInteractionIfNew(noteId, interactionType) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('recordNoteInteractionIfNew requires noteId');
    }
    if (typeof interactionType !== 'string' || interactionType.length === 0) {
        throw new Error('recordNoteInteractionIfNew requires interactionType');
    }
    primeActiveSearchInteractionState();
    const tabId = getActiveTabId();
    const state = stateByTabId[tabId];
    if (state.engagedNoteId === noteId || state.pendingNoteId === noteId) {
        return false;
    }
    state.pendingNoteId = noteId;
    const response = await NotesAPI.recordNoteInteraction(noteId, interactionType).then(
        (payload) => payload,
        (error) => {
            state.pendingNoteId = null;
            throw error;
        },
    );
    if (!response || typeof response !== 'object') {
        state.pendingNoteId = null;
        throw new Error('Note interaction response missing');
    }
    if (typeof response.credited !== 'boolean') {
        state.pendingNoteId = null;
        throw new Error('Note interaction response requires credited boolean');
    }
    state.pendingNoteId = null;
    state.engagedNoteId = noteId;
    return response.credited;
}

export function resetNoteInteractionStateForTests() {
    for (const tabId of Object.keys(stateByTabId)) {
        delete stateByTabId[tabId];
    }
}
