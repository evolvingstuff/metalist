import { ModeManager } from './modules/mode-manager/mode-manager-controller.js';
import { StateMachine } from './modules/state-machine/state-machine-controller.js';
import { CONFIG } from './modules/config.js';
import { DOMUtils } from './modules/dom-utils.js';

/**
 * Initialize the application when the DOM is ready
 */
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOMContentLoaded fired');
    
    // Add direct log to see if this code runs
    console.log('+++ main.js: About to initialize ModeManager');
    
    // Initialize ModeManager BEFORE state machine
    try {
        // Check if ModeManager loaded properly
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
    
    // Initialize state machine
    StateMachine.init();
    console.log('StateMachine initialized');
    
    // Add keyboard event handler
    document.addEventListener('keydown', (e) => {
        StateMachine.handleRawEvent('KeyDown', e);
    });

    // Handle all clicks through click handler
    document.addEventListener('click', (e) => {
        StateMachine.handleRawEvent('Click', e);
    });

    // Handle all input events (for note content changes)
    document.addEventListener('input', (e) => {
        StateMachine.handleRawEvent('Input', e);
    });

    // Prevent "phantom" cursor appearing when focusing notes outside their bounds
    // This can happen when clicking below/between notes since they are contenteditable
    // TODO: this is a hack we should revisit
    document.addEventListener('focus', (e) => {
        const noteContent = e.target.closest('.note-content');
        if (noteContent) {
            const rect = noteContent.getBoundingClientRect();
            if (!(e.clientY >= rect.top && e.clientY <= rect.bottom)) {
                window.getSelection().removeAllRanges();
            }
        }
    }, true);  // Capture phase ensures we handle focus before contenteditable processing

    if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
        console.log('Application initialized successfully');
    }
});

// Handle unhandled promise rejections
window.addEventListener('unhandledrejection', event => {
    console.error('Unhandled promise rejection:', event.reason);
});