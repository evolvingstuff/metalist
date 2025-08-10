import { ModeManager } from './modules/mode-manager/mode-manager-controller.js';
import { CONFIG } from './modules/config.js';
import { DOMUtils } from './modules/dom-utils.js';
import { Auth } from './modules/auth.js';
import { ErrorHandler } from './modules/error-handler.js';
import { ConnectivityMonitor } from './modules/connectivity-monitor.js';

document.addEventListener('DOMContentLoaded', async () => {
    console.log('DOMContentLoaded fired');

    // Make ModeManager available globally for post-login initialization
    window.ModeManager = ModeManager;
    
    // Start connectivity monitoring (runs regardless of auth state)
    ConnectivityMonitor.start();

    // Initialize authentication first
    console.log('+++ main.js: About to initialize Auth');
    try {
        const isAuthOk = await Auth.init();
        console.log('+++ main.js: Auth init() completed, authOk:', isAuthOk);
        
        // Only initialize ModeManager if auth is OK
        if (isAuthOk) {
            console.log('+++ main.js: About to initialize ModeManager');
            
            if (!ModeManager) {
                console.error('+++ main.js: ModeManager not defined!');
            } else {
                console.log('+++ main.js: ModeManager exists, calling init()');
                ModeManager.init();
                console.log('+++ main.js: ModeManager init() completed');
            }
        } else {
            console.log('+++ main.js: Skipping ModeManager init due to auth requirement');
        }
    } catch (error) {
        console.error('+++ main.js: Error initializing:', error);
    }

    document.addEventListener('focus', (e) => {
        const noteContent = e.target.closest('.note-content');
        if (noteContent) {
            const rect = noteContent.getBoundingClientRect();
            if (!(e.clientY >= rect.top && e.clientY <= rect.bottom)) {
                window.getSelection().removeAllRanges();
            }
        }
    }, true);  

    if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
        console.log('Application initialized successfully');
    }
});

window.addEventListener('unhandledrejection', event => {
    console.error('Unhandled promise rejection:', event.reason);
});