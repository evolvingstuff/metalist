import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { ErrorHandler } from '../../error-handler.js';

let pollingInterval = null;
let lastTokenRefreshAt = 0;

const TOKEN_REFRESH_INTERVAL_MS = 60_000; // minimum time between auth refresh calls

export function startPolling() {
    // Unified polling: check connectivity and updates
    pollingInterval = setInterval(() => {
        checkConnectivityAndUpdates();
    }, 500);  // Poll every 500ms
    
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

    try {
        const response = await fetch('/api/auth/sessions', {
            method: 'GET',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (response.ok) {
            lastTokenRefreshAt = Date.now();
            Logger.logDebug('Token refreshed due to user activity');
        }
    } catch (error) {
        Logger.logError('Failed to refresh token on activity', error);
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
        
        // Add auth token if it exists
        const authToken = localStorage.getItem('auth_token');
        
        const response = await fetch('/api/notes/check-updates', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                ...(authToken && { 'Authorization': `Bearer ${authToken}` })
            },
            body: JSON.stringify({
                clientId: ModeContext.clientId,
                lastUpdateUUID: ModeContext.lastUpdateUUID
            })
        });
        
        if (response.ok) {
            // Connection is working - handle restoration if needed
            ErrorHandler.handleConnectionRestored();
            
            const data = await response.json();
            
            if (data.needsUpdate) {
                Logger.logDebug('Update detected, refreshing view', {
                    currentUUID: data.currentUpdateUUID,
                    lastKnown: ModeContext.lastUpdateUUID
                });
                
                // Update our UUID before refresh
                ModeContext.setLastUpdateUUID(data.currentUpdateUUID);
                
                // Trigger refresh
                const { actionRefreshAndMaybeSelect } = await import('../actions/ui-actions.js');
                await actionRefreshAndMaybeSelect();
            }
        } else {
            // Use error handler for HTTP errors
            ErrorHandler.handleApiError(null, response);
        }
    } catch (error) {
        // Always show network errors immediately and loudly
        ErrorHandler.handleApiError(error);
        Logger.logError('Sync polling error', error);
    }
}
