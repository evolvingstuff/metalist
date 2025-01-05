import { StateMachine } from './modules/state-machine/state-machine-controller.js';
import { CONFIG } from './modules/config.js';

/**
 * Initialize the application when the DOM is ready
 */
document.addEventListener('DOMContentLoaded', () => {
    try {
        // Initialize state machine
        StateMachine.init();
        
        // Add button click handler
        const addButton = document.querySelector('.add-note');
        if (addButton) {
            addButton.addEventListener('click', (e) => {
                e.preventDefault();
                StateMachine.handleRawEvent('AddButtonClick', e);
            });
        }

        // Add keyboard event handler
        document.addEventListener('keydown', (e) => {
            StateMachine.handleRawEvent('KeyDown', e);
        });

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