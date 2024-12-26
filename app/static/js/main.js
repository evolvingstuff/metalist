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

        // Check for new note to edit
        const newNoteId = localStorage.getItem('newNoteId');
        const cursorPosition = localStorage.getItem('cursorPosition');
        
        if (newNoteId) {
            const newNote = document.querySelector(`[data-id="${newNoteId}"]`);
            if (newNote) {
                NoteState.startEditing(newNote);
                if (cursorPosition === 'end') {
                    DOMUtils.focusNote(newNote);  // This already puts cursor at end
                }
                localStorage.removeItem('newNoteId');
                localStorage.removeItem('cursorPosition');
            }
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