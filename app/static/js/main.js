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

        // Check for new note to edit
        const newNoteId = localStorage.getItem('newNoteId');
        if (newNoteId) {
            const newNote = document.querySelector(`[data-id="${newNoteId}"]`);
            if (newNote) {
                StateMachine.handleMappedEvent({
                    type: 'START_EDITING',
                    data: {
                        nextNote: newNote,
                        cursorPosition: localStorage.getItem('cursorPosition') || 'end'
                    }
                });
                localStorage.removeItem('newNoteId');
                localStorage.removeItem('cursorPosition');
            }
        }

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