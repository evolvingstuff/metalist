import { ModeManager } from './modules/mode-manager/mode-manager-controller.js';
import { StateMachine } from './modules/state-machine/state-machine-controller.js';
import { CONFIG } from './modules/config.js';
import { DOMUtils } from './modules/dom-utils.js';

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOMContentLoaded fired');

    console.log('+++ main.js: About to initialize ModeManager');

    try {
                                
        if (!ModeManager) {
            console.error('+++ main.js: ModeManager not defined!');
        } else {
            console.log('+++ main.js: ModeManager exists, calling init()');
            ModeManager.init();
            console.log('+++ main.js: ModeManager init() completed');
        }
    } catch (error) {
        console.error('+++ main.js: Error initializing ModeManager:', error);
    }

    console.log('StateMachine disabled for ModeManager testing');

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