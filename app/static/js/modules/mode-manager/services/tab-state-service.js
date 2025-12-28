import { CONFIG } from '../../config.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';
import { ErrorHandler } from '../../error-handler.js';

const TAB_STATE_ENDPOINT = CONFIG.API.NOTES.TAB_STATE;
const SYNC_DEBOUNCE_MS = 1000;

let pendingPayload = null;
let flushTimeoutId = null;
let lastSignature = null;
let scrollIntervalId = null;

export async function initializeTabStateService() {
    ModeContext.setTabStateUpdateHook(handleTabStateMutation);
    const serverState = await fetchTabState();
    ModeContext.hydrateTabState(serverState, { emitUpdate: false });
    ModeContext.setTabStateVersion(typeof serverState.version === 'number' ? serverState.version : 0);
    lastSignature = serializeState(serverState);
    startScrollWatcher();
    return serverState;
}

function handleTabStateMutation({ payload }) {
    pendingPayload = payload;
    scheduleFlush();
}

function scheduleFlush() {
    if (flushTimeoutId !== null) {
        return;
    }
    flushTimeoutId = window.setTimeout(async () => {
        flushTimeoutId = null;
        await flushTabState();
    }, SYNC_DEBOUNCE_MS);
}

async function flushTabState() {
    if (!pendingPayload) {
        return;
    }
    const snapshot = pendingPayload;
    pendingPayload = null;
    const signature = serializeState(snapshot);
    if (signature === lastSignature) {
        return;
    }
    if (ModeContext.isLoading) {
        pendingPayload = snapshot;
        scheduleFlush();
        return;
    }
    try {
        const response = await callTabStateApi('POST', snapshot);
        ModeContext.setTabStateVersion(typeof response.version === 'number' ? response.version : 0);
        lastSignature = serializeState(response);
    } catch (error) {
        console.error('[TabStateService] Failed to persist tab state', error);
        pendingPayload = snapshot;
    }
}

async function fetchTabState() {
    try {
        return await callTabStateApi('GET');
    } catch (error) {
        console.error('[TabStateService] Failed to fetch tab state', error);
        throw error;
    }
}

async function callTabStateApi(method, body = null) {
    const headers = { 'Content-Type': 'application/json' };
    const tabId = sessionStorage.getItem('metalist_tab_id');
    if (!tabId) {
        throw new Error('metalist_tab_id missing from sessionStorage');
    }
    headers['X-Metalist-Tab-Id'] = tabId;
    const authToken = localStorage.getItem('auth_token');
    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }
    try {
        const response = await fetch(TAB_STATE_ENDPOINT, {
            method,
            headers,
            body: body ? JSON.stringify(body) : undefined,
        });
        if (!response.ok) {
            ErrorHandler.handleApiError(null, response);
            throw new Error(`tab-state ${method} failed with status ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        if (!(error instanceof Error) || !error.message.includes('failed with status')) {
            ErrorHandler.handleApiError(error);
        }
        throw error;
    }
}

function startScrollWatcher() {
    if (scrollIntervalId !== null) {
        clearInterval(scrollIntervalId);
    }
    let lastScrollY = getCurrentScrollY();
    scrollIntervalId = window.setInterval(() => {
        if (ModeContext.isLoading) {
            return;
        }
        const current = getCurrentScrollY();
        if (current !== lastScrollY) {
            lastScrollY = current;
            ModeContext.updateActiveTabScroll(current);
        }
    }, SYNC_DEBOUNCE_MS);
}

function getCurrentScrollY() {
    return Math.max(0, Math.round(window.scrollY));
}

function serializeState(state) {
    if (!state) {
        return '';
    }
    return JSON.stringify(state);
}
