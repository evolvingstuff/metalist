import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { ErrorHandler } from '../../error-handler.js';
import { CONFIG } from '../../config.js';

let pollingInterval = null;
let lastTokenRefreshAt = 0;
const TOKEN_REFRESH_INTERVAL_MS = 60_000; // minimum time between auth refresh calls

export function startPolling() {
    // Unified polling: check connectivity and updates
    pollingInterval = setInterval(() => {
        checkConnectivityAndUpdates();
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

    try {
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
        } else {
            Logger.logError('Token refresh request failed', response.statusText);
            ErrorHandler.handleApiError(null, response);
        }
    } catch (error) {
        Logger.logError('Failed to refresh token on activity', error);
        ErrorHandler.handleApiError(error);
    }
}

async function checkConnectivityAndUpdates() {
    try {
        // Check if user has been active and refresh token if needed
        if (ModeContext.userActivity) {
            const now = Date.now();
            if (now - lastTokenRefreshAt >= TOKEN_REFRESH_INTERVAL_MS) {
                await refreshTokenOnActivity();
            } else {
                Logger.logDebug('User activity detected but token refresh throttled', {
                    timeSinceLastRefresh: now - lastTokenRefreshAt
                });
            }

            ModeContext.setUserActivity(false);
        }

        await pingAuthStatus();
    } catch (error) {
        // Always show network errors immediately and loudly
        ErrorHandler.handleApiError(error);
        Logger.logError('Sync polling error', error);
    }
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
