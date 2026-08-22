import { NotesAPI } from '../../api-client.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';
import { getLimitNoteCreditsPerSearchContext } from './search-suggestion-windows-service.js';

const stateByTabId = Object.create(null);
let activeContextTabId = null;
let activeContextQuery = null;

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
    let enteredContext = activeContextTabId !== tabId;
    if (activeContextQuery !== query) {
        enteredContext = true;
    }
    activeContextTabId = tabId;
    activeContextQuery = query;
    if (enteredContext) {
        stateByTabId[tabId] = {
            query,
            creditedNoteIds: new Set(),
            pendingNoteIds: new Set(),
        };
        return;
    }
    if (!Object.prototype.hasOwnProperty.call(stateByTabId, tabId)) {
        stateByTabId[tabId] = {
            query,
            creditedNoteIds: new Set(),
            pendingNoteIds: new Set(),
        };
        return;
    }
    const state = stateByTabId[tabId];
    if (state.query !== query) {
        stateByTabId[tabId] = {
            query,
            creditedNoteIds: new Set(),
            pendingNoteIds: new Set(),
        };
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
    const shouldLimitCredits = getLimitNoteCreditsPerSearchContext();
    if (
        shouldLimitCredits
        && (state.creditedNoteIds.has(noteId) || state.pendingNoteIds.has(noteId))
    ) {
        return false;
    }
    state.pendingNoteIds.add(noteId);
    const response = await NotesAPI.recordNoteInteraction(noteId, interactionType).then(
        (payload) => payload,
        (error) => {
            state.pendingNoteIds.delete(noteId);
            throw error;
        },
    );
    if (!response || typeof response !== 'object') {
        state.pendingNoteIds.delete(noteId);
        throw new Error('Note interaction response missing');
    }
    if (typeof response.credited !== 'boolean') {
        state.pendingNoteIds.delete(noteId);
        throw new Error('Note interaction response requires credited boolean');
    }
    state.pendingNoteIds.delete(noteId);
    if (response.credited) {
        state.creditedNoteIds.add(noteId);
    }
    return response.credited;
}

export async function recordStructuralNoteInteractionIfMoved(noteId, interactionType, mutationResponse) {
    if (typeof noteId !== 'string' || noteId.length === 0) {
        throw new Error('recordStructuralNoteInteractionIfMoved requires noteId');
    }
    if (interactionType !== 'move' && interactionType !== 'indent' && interactionType !== 'outdent') {
        throw new Error('Structural interaction type must be move, indent, or outdent');
    }
    if (mutationResponse === null || typeof mutationResponse !== 'object') {
        throw new Error('Structural interaction mutation response missing');
    }
    if (mutationResponse.status === 'noop') {
        return false;
    }
    if (mutationResponse.status !== 'moved') {
        throw new Error(`Unknown structural interaction status: ${mutationResponse.status}`);
    }
    return recordNoteInteractionIfNew(noteId, interactionType);
}

export function resetNoteInteractionStateForTests() {
    for (const tabId of Object.keys(stateByTabId)) {
        delete stateByTabId[tabId];
    }
    activeContextTabId = null;
    activeContextQuery = null;
}
