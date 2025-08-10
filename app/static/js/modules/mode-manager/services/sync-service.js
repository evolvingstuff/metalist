import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { ErrorHandler } from '../../error-handler.js';

let syncPollingInterval = null;

export function startSyncPolling() {
    // Poll every 500ms when not editing
    syncPollingInterval = setInterval(() => {
        if (!ModeContext.isEditing) {  // Only poll when not editing
            checkForUpdates();
        }
    }, 500);
    
    Logger.logInit('Multi-device sync polling started');
}

export function stopSyncPolling() {
    if (syncPollingInterval) {
        clearInterval(syncPollingInterval);
        syncPollingInterval = null;
        Logger.logDebug('Sync polling stopped');
    }
}

async function checkForUpdates() {
    try {
        const response = await fetch('/api/notes/check-updates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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