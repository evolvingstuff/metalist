import { CONFIG } from './config.js';
import { DOMUtils } from './dom-utils.js';
import { NotesAPI } from './api-client.js';
import { NoteStateMachine } from './note-state-machine.js';

/**
 * IMPORTANT ASSUMPTIONS AND GOTCHAS:
 * 
 * 1. State Coordination:
 *    - Acts as facade for state machine transitions
 *    - Maintains local state for backward compatibility
 *    - Auto-save system independent of state machine
 * 
 * 2. Content Management:
 *    - Content saves triggered by state machine exit
 *    - Local lastSavedContent for change detection
 *    - Auto-save timeout cleared on state changes
 * 
 * 3. Legacy Support:
 *    - Maintains parallel implementations
 *    - Legacy methods must match state machine behavior
 *    - Feature flag might change at runtime
 * 
 * 4. Error Handling:
 *    - Failed transitions must not corrupt state
 *    - Save operations must be idempotent
 *    - Cleanup must happen even on errors
 */

/**
 * Manages note state and transitions
 */
export const NoteState = {
    currentEditingNote: null,
    lastSavedContent: null,
    inactivityTimeout: null,

    /**
     * Start editing a note
     */
    async startEditing(noteElement) {
        if (!CONFIG.FEATURES.USE_STATE_MACHINE) {
            return this.startEditingLegacy(noteElement);
        }

        // If we're already in editing state with this note, do nothing
        if (NoteStateMachine.state === 'editing' && 
            NoteStateMachine.data.currentNote === noteElement) {
            return;
        }

        // If we're in search state, let the blur handler handle it
        if (NoteStateMachine.state === 'searching') {
            return;
        }

        // Otherwise proceed with normal transition
        await NoteStateMachine.transition('editing', {
            currentNote: noteElement,
            lastSavedContent: DOMUtils.getNoteContentText(noteElement)
        });

        // Update our local references
        this.currentEditingNote = noteElement;
        this.lastSavedContent = DOMUtils.getNoteContentText(noteElement);
        
        // Set up auto-save
        this.setupInactivityTimeout();
    },

    /**
     * Start search mode
     */
    async startSearch(query = '') {
        if (!CONFIG.FEATURES.USE_STATE_MACHINE) return;

        // State machine handles the transition
        await NoteStateMachine.transition('searching', {
            searchQuery: query
        });
    },

    /**
     * Save the current note
     */
    async saveCurrentNoteWithStateMachine() {
        if (!this.currentEditingNote) return;

        const content = DOMUtils.getNoteContentText(this.currentEditingNote);
        if (content === this.lastSavedContent) return;

        const noteId = DOMUtils.getNoteId(this.currentEditingNote);
        await NotesAPI.updateNote(noteId, content);
        
        this.lastSavedContent = content;
        console.log('Note saved:', noteId);
    },

    /**
     * Set up auto-save timeout
     */
    setupInactivityTimeout() {
        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
        }

        this.inactivityTimeout = setTimeout(async () => {
            await this.saveCurrentNoteWithStateMachine();
        }, CONFIG.AUTO_SAVE_DELAY);
    },

    /**
     * Handle content changes
     */
    handleContentChange() {
        if (!this.currentEditingNote) return;
        this.setupInactivityTimeout();
    },

    // Keep legacy methods for backward compatibility
    startEditingLegacy(noteElement) {
        // ... existing legacy code ...
    }
}; 