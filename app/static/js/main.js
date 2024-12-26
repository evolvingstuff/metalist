import { CONFIG } from './modules/config.js';
import { NotesAPI } from './modules/api-client.js';
import { DOMUtils } from './modules/dom-utils.js';
import { NoteState } from './modules/note-state.js';
import { EventHandlers } from './modules/event-handlers.js';

/**
 * Initialize the application when the DOM is ready
 */
document.addEventListener('DOMContentLoaded', () => {
    try {
        // Initialize modules in dependency order
        EventHandlers.init();

        if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
            console.log('Application initialized successfully');
        }
    } catch (error) {
        console.error('Failed to initialize application:', error);
        alert('Failed to initialize application. Please refresh the page.');
    }
});

// Handle unhandled promise rejections
window.addEventListener('unhandledrejection', event => {
    console.error('Unhandled promise rejection:', event.reason);
});