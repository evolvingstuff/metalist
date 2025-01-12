import { StateMachine } from './modules/state-machine/state-machine-controller.js';
import { CONFIG } from './modules/config.js';
import { DOMUtils } from './modules/dom-utils.js';

/**
 * Initialize the application when the DOM is ready
 */
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOMContentLoaded fired');
    try {
        // Initialize state machine
        StateMachine.init();
        console.log('StateMachine initialized');
        
        // Add keyboard event handler
        document.addEventListener('keydown', (e) => {
            try {
                StateMachine.handleRawEvent('KeyDown', e);
            } catch (err) {
                console.error('Error handling keydown:', err);
            }
        });

        // Handle all clicks through click handler
        document.addEventListener('click', (e) => {
            try {
                StateMachine.handleRawEvent('Click', e);
            } catch (err) {
                console.error('Error handling click:', err);
            }
        });

        // Add search input focus handler
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('focus', (e) => {
                try {
                    StateMachine.handleRawEvent('SearchFocus', e);
                } catch (err) {
                    console.error('Error handling search focus:', err);
                }
            });
        }

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
    } catch (error) {
        console.error('Initialization failed:', error);
    }
});

// Handle unhandled promise rejections
window.addEventListener('unhandledrejection', event => {
    console.error('Unhandled promise rejection:', event.reason);
});