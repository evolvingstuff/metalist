import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

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
        }
    } catch (error) {
        // Silently handle polling errors to avoid spam
        // Only log unexpected errors
        if (!error.message.includes('fetch')) {
            Logger.logError('Sync polling error', error);
        }
    }
}