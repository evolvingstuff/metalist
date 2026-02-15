import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { ErrorHandler } from '../../error-handler.js';
import { CONFIG } from '../../config.js';
import { CommandGate } from './command-gate-service.js';

let pollingInterval = null;
let lastTokenRefreshAt = 0;
const TOKEN_REFRESH_INTERVAL_MS = 60_000; // minimum time between auth refresh calls
const RESTORE_TRANSITION_UNTIL_KEY = 'metalist_restore_transition_until_ms';


function _isRestoreTransitionActive() {
    const rawValue = sessionStorage.getItem(RESTORE_TRANSITION_UNTIL_KEY);
    if (rawValue === null) {
        return false;
    }
    if (!/^[0-9]+$/.test(rawValue)) {
        sessionStorage.removeItem(RESTORE_TRANSITION_UNTIL_KEY);
        return false;
    }
    const untilMs = Number.parseInt(rawValue, 10);
    if (!Number.isInteger(untilMs)) {
        sessionStorage.removeItem(RESTORE_TRANSITION_UNTIL_KEY);
        return false;
    }
    if (Date.now() >= untilMs) {
        sessionStorage.removeItem(RESTORE_TRANSITION_UNTIL_KEY);
        return false;
    }
    return true;
}

export function startPolling() {
    // Unified polling: check connectivity and updates
    pollingInterval = setInterval(() => {
        checkConnectivityAndUpdates().catch((error) => {
            ErrorHandler.handleApiError(error, null);
            Logger.logError('Sync polling error', error);
        });
    }, CONFIG.SYNC.POLL_INTERVAL_MS);

    Logger.logInit('Unified polling started (connectivity + updates)');
}

export function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
        Logger.logDebug('Unified polling stopped');
    }
}

async function refreshTokenOnActivity() {
    const authToken = localStorage.getItem('auth_token');
    if (!authToken) {
        return;
    }

    const tabId = sessionStorage.getItem('metalist_tab_id');
    if (!tabId) {
        throw new Error('metalist_tab_id missing from sessionStorage');
    }

    const response = await fetch(CONFIG.API.AUTH.SESSIONS, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${authToken}`,
            'X-Metalist-Tab-Id': tabId
        }
    });

    if (response.ok) {
        lastTokenRefreshAt = Date.now();
        Logger.logDebug('Token refreshed due to user activity');
        return;
    }

    Logger.logError('Token refresh request failed', response.statusText);
    ErrorHandler.handleApiError(null, response);
}

async function checkConnectivityAndUpdates() {
    if (_isRestoreTransitionActive()) {
        return;
    }
    if (CommandGate.isBusy()) {
        return;
    }
    if (ModeContext.userActivity) {
        const now = Date.now();
        if (now - lastTokenRefreshAt >= TOKEN_REFRESH_INTERVAL_MS) {
            await refreshTokenOnActivity().finally(() => {
                ModeContext.setUserActivity(false);
            });
        } else {
            Logger.logDebug('User activity detected but token refresh throttled', {
                timeSinceLastRefresh: now - lastTokenRefreshAt
            });
            ModeContext.setUserActivity(false);
        }
    }

    await pingAuthStatus();
}

async function pingAuthStatus() {
    const authToken = localStorage.getItem('auth_token');
    const tabId = sessionStorage.getItem('metalist_tab_id');
    if (!tabId) {
        throw new Error('metalist_tab_id missing from sessionStorage');
    }
    const headers = {
        'X-Metalist-Tab-Id': tabId,
        ...(authToken && { 'Authorization': `Bearer ${authToken}` })
    };

    const response = await fetch(CONFIG.API.AUTH.STATUS, {
        method: 'GET',
        headers
    });

    if (response.ok) {
        ErrorHandler.handleConnectionRestored();
        return;
    }

    // Use centralized handler for HTTP errors
    ErrorHandler.handleApiError(null, response);
}
