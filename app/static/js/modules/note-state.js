import { CONFIG } from './config.js';
import { NotesAPI } from './api-client.js';
import { DOMUtils } from './dom-utils.js';

/**
 * Manages the state of notes and editing
 */
export const NoteState = {
    currentEditingNote: null,
    lastSavedContent: null,
    inactivityTimeout: null,
    
    /**
     * Start editing a note
     */
    startEditing(noteElement) {
        if (this.currentEditingNote === noteElement) {
            return; // Already editing this note
        }

        // Clean up any previous editing state
        this.finishEditing();

        // Set up new editing state
        this.currentEditingNote = noteElement;
        this.lastSavedContent = DOMUtils.getNoteContentText(noteElement);
        DOMUtils.setNoteEditable(noteElement, true);
        DOMUtils.focusNote(noteElement);

        if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
            console.log('Started editing note:', DOMUtils.getNoteId(noteElement));
        }
    },

    /**
     * Handle content changes during editing
     */
    handleContentChange() {
        if (!this.currentEditingNote) return;

        // Clear any existing timeout
        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
        }

        // Set new timeout for auto-save
        this.inactivityTimeout = setTimeout(() => {
            this.saveCurrentNote();
        }, CONFIG.INACTIVITY_TIMEOUT);
    },

    /**
     * Save the current note's content
     */
    async saveCurrentNote() {
        if (!this.currentEditingNote) return;

        const currentContent = DOMUtils.getNoteContentText(this.currentEditingNote);
        
        // Only save if content has changed
        if (currentContent !== this.lastSavedContent) {
            const noteId = DOMUtils.getNoteId(this.currentEditingNote);
            
            if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
                console.log('Saving note:', noteId);
            }

            await NotesAPI.updateNote(noteId, currentContent);
            this.lastSavedContent = currentContent;
        }
    },

    /**
     * Finish editing the current note
     */
    async finishEditing() {
        if (!this.currentEditingNote) return;

        // Save any pending changes
        await this.saveCurrentNote();

        // Clean up
        DOMUtils.setNoteEditable(this.currentEditingNote, false);
        
        if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
            console.log('Finished editing note:', DOMUtils.getNoteId(this.currentEditingNote));
        }

        this.currentEditingNote = null;
        this.lastSavedContent = null;
        
        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
            this.inactivityTimeout = null;
        }
    },

    /**
     * Check if a specific note is being edited
     */
    isEditing(noteElement) {
        return this.currentEditingNote === noteElement;
    },

    /**
     * Get the currently editing note element
     */
    getCurrentEditingNote() {
        return this.currentEditingNote;
    },

    /**
     * Check if any note is currently being edited
     */
    isAnyNoteEditing() {
        return this.currentEditingNote !== null;
    },

    /**
     * Force save all pending changes
     */
    async forceSaveAll() {
        await this.saveCurrentNote();
    }
}; 