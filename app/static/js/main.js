import { ModeManager } from './modules/mode-manager/mode-manager-controller.js';
import { CONFIG } from './modules/config.js';
import { DOMUtils } from './modules/dom-utils.js';
import { Auth } from './modules/auth.js';
import { ErrorHandler } from './modules/error-handler.js';
import { ActivityTracker } from './modules/activity-tracker.js';
import { CommandPalette } from './modules/command-palette/command-palette-controller.js';
document.addEventListener('DOMContentLoaded', async () => {
    console.log('DOMContentLoaded fired');

    // Make ModeManager available globally for post-login initialization
    window.ModeManager = ModeManager;
    
    // Start activity tracking for token refresh
    ActivityTracker.start();

    // Initialize authentication first
    console.log('+++ main.js: About to initialize Auth');
    const isAuthOk = await Auth.init();
    console.log('+++ main.js: Auth init() completed, authOk:', isAuthOk);

    // Only initialize ModeManager if auth is OK
    if (isAuthOk) {
        console.log('+++ main.js: About to initialize ModeManager');
        ModeManager.init({});
        console.log('+++ main.js: ModeManager init() completed');

        await CommandPalette.init();
    } else {
        console.log('+++ main.js: Skipping ModeManager init due to auth requirement');
    }

    document.addEventListener('focus', (e) => {
        const target = e && e.target;
        if (!target) {
            return;
        }

        let element = null;
        if (typeof target.closest === 'function') {
            element = target;
        } else if (target.nodeType === 3 && target.parentElement && typeof target.parentElement.closest === 'function') {
            element = target.parentElement;
        } else {
            return;
        }

        const noteContent = element.closest('.note-content');
        if (noteContent) {
            if (typeof e.clientY !== 'number') {
                return;
            }
            const rect = noteContent.getBoundingClientRect();
            if (!(e.clientY >= rect.top && e.clientY <= rect.bottom)) {
                const selection = window.getSelection();
                if (selection) {
                    selection.removeAllRanges();
                }
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
