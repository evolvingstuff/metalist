import { CONFIG } from '../../config.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';
import { ErrorHandler } from '../../error-handler.js';

const TAB_STATE_ENDPOINT = CONFIG.API.NOTES.TAB_STATE;

let lastSignature = null;
let scrollListenerAttached = false;
let pendingScrollFrame = null;
let lastScrollY = 0;
let pendingTabId = null;

export async function initializeTabStateService() {
    const serverState = await fetchTabState();
    ModeContext.hydrateTabState(serverState, { emitUpdate: false });
    ModeContext.setTabStateVersion(typeof serverState.version === 'number' ? serverState.version : 0);
    lastSignature = serializeState(serverState);
    startScrollWatcher();
    return serverState;
}

export async function persistTabStateSnapshot() {
    const snapshot = ModeContext.getTabStatePayload();
    const signature = serializeState(snapshot);
    if (signature === lastSignature) {
        return;
    }
    const response = await callTabStateApi('POST', snapshot);
    ModeContext.setTabStateVersion(typeof response.version === 'number' ? response.version : 0);
    lastSignature = serializeState(response);
}

async function fetchTabState() {
    return await callTabStateApi('GET');
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
}

function startScrollWatcher() {
    if (scrollListenerAttached) {
        return;
    }
    lastScrollY = getCurrentScrollY();
    window.addEventListener('scroll', handleScrollEvent, { passive: true });
    scrollListenerAttached = true;
}

function handleScrollEvent() {
    if (ModeContext.isLoading) {
        return;
    }
    if (pendingScrollFrame !== null) {
        return;
    }
    const sourceTabId = ModeContext.activeTabId;
    pendingTabId = sourceTabId;
    pendingScrollFrame = window.requestAnimationFrame(() => {
        pendingScrollFrame = null;
        const current = getCurrentScrollY();
        if (current !== lastScrollY) {
            lastScrollY = current;
            ModeContext.updateTabScroll(pendingTabId || ModeContext.activeTabId, current, true);
        }
        pendingTabId = null;
    });
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
