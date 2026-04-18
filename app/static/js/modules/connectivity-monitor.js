/**
 * Connectivity Monitor - Dedicated service for checking server connectivity
 * Runs independently of UI state (editing, searching, etc.)
 */

import { ModeContextInstance as ModeContext } from './mode-manager/mode-context.js';
import { CONFIG } from './config.js';
import { ErrorHandler } from './error-handler.js';

let connectivityInterval = null;
const CONNECTIVITY_CHECK_INTERVAL = 2000; // Check every 2 seconds

export const ConnectivityMonitor = {
    handleConnectivityFailure(error) {
        console.log('[ConnectivityMonitor] Connectivity check failed:', error.message);
        ErrorHandler.handleApiError(error, null);
    },

    
    /**
     * Start monitoring server connectivity
     */
    start() {
        if (connectivityInterval) {
            console.warn('[ConnectivityMonitor] Already running');
            return;
        }
        
        console.log('[ConnectivityMonitor] Starting connectivity monitoring');
        
        // Check immediately
        void this.checkConnectivity().catch((error) => {
            this.handleConnectivityFailure(error);
        });
        
        // Then check periodically
        connectivityInterval = setInterval(() => {
            void this.checkConnectivity().catch((error) => {
                this.handleConnectivityFailure(error);
            });
        }, CONNECTIVITY_CHECK_INTERVAL);
    },
    
    /**
     * Stop monitoring server connectivity
     */
    stop() {
        if (connectivityInterval) {
            clearInterval(connectivityInterval);
            connectivityInterval = null;
            console.log('[ConnectivityMonitor] Stopped connectivity monitoring');
        }
    },
    
    /**
     * Check server connectivity with a lightweight ping endpoint
     */
    async checkConnectivity() {
        const authToken = localStorage.getItem('auth_token');
        const tabId = sessionStorage.getItem('metalist_tab_id');
        if (!tabId) {
            throw new Error('metalist_tab_id missing from sessionStorage');
        }
        const headers = {};

        headers['X-Metalist-Tab-Id'] = tabId;

        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000); // 3 second timeout

        const response = await fetch(CONFIG.API.AUTH.STATUS, {
            method: 'GET',
            headers: headers,
            signal: controller.signal
        }).finally(() => {
            clearTimeout(timeoutId);
        });

        if (response.ok) {
            ErrorHandler.handleConnectionRestored();
        } else if (response.status === 401) {
            ErrorHandler.handleApiError(null, response);
        } else {
            console.log('[ConnectivityMonitor] Server returned error:', response.status);
        }
    },
    
    /**
     * Force an immediate connectivity check
     */
    checkNow() {
        void this.checkConnectivity().catch((error) => {
            this.handleConnectivityFailure(error);
        });
    }
};

// Export for global access if needed
window.ConnectivityMonitor = ConnectivityMonitor;
