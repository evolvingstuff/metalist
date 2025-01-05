import { StateMachine } from './modules/state-machine/state-machine-controller.js';
import { CONFIG } from './modules/config.js';
import { DOMUtils } from './modules/dom-utils.js';

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

        // Handle clicks on notes to enter editing state
        // and clicks outside interactive elements to exit editing state
        document.addEventListener('click', (e) => {
            const noteContent = e.target.closest('.note-content');
            if (noteContent) {
                StateMachine.handleRawEvent('NoteContentClick', {
                    noteElement: noteContent.closest('.note')
                });
                return;
            }

            // If clicked anywhere except interactive elements, exit editing
            if (!e.target.closest('.interactive')) {
                StateMachine.handleRawEvent('ClickOutsideNote');
            }
        });

        // Prevent "phantom" cursor appearing when focusing notes outside their bounds
        // This can happen when clicking below/between notes since they are contenteditable
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