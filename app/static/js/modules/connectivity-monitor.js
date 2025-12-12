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
        this.checkConnectivity();
        
        // Then check periodically
        connectivityInterval = setInterval(() => {
            this.checkConnectivity();
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
        try {
            // Add auth token if it exists
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
            
            // Use a lightweight endpoint - auth status is perfect for this
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 3000); // 3 second timeout
            
            const response = await fetch(CONFIG.API.AUTH.STATUS, {
                method: 'GET',
                headers: headers,
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                // Server is reachable
                ErrorHandler.handleConnectionRestored();
            } else if (response.status === 401) {
                // Authentication error - different from connectivity issue
                ErrorHandler.handleApiError(null, response);
            } else {
                // Server error but still connected
                console.log('[ConnectivityMonitor] Server returned error:', response.status);
                // Don't show network error for non-network issues
            }
            
        } catch (error) {
            // Network error - server unreachable
            console.log('[ConnectivityMonitor] Connectivity check failed:', error.message);
            ErrorHandler.handleApiError(error);
        }
    },
    
    /**
     * Force an immediate connectivity check
     */
    checkNow() {
        this.checkConnectivity();
    }
};

// Export for global access if needed
window.ConnectivityMonitor = ConnectivityMonitor;
