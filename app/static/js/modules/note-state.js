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
        if (this.currentEditingNote === noteElement) return;
        
        // If editing another note, finish that first
        if (this.currentEditingNote) {
            this.finishEditing();
        }

        // Set state first
        this.currentEditingNote = noteElement;
        this.lastSavedContent = DOMUtils.getNoteContentText(noteElement);
        
        // Then update DOM
        const content = DOMUtils.getNoteContent(noteElement);
        content.contentEditable = true;
        noteElement.classList.add(CONFIG.CLASSES.EDITING);
        content.focus();
        
        if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
            console.log('Started editing note:', DOMUtils.getNoteId(noteElement));
        }

        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
        }

        this.inactivityTimeout = setInterval(() => {
            this.saveCurrentNote();
        }, CONFIG.INACTIVITY_TIMEOUT);
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
     * Save the current note's content and cursor position
     */
    async saveCurrentNote() {
        if (!this.currentEditingNote) return;

        const currentContent = DOMUtils.getNoteContentText(this.currentEditingNote);
        const cursorPosition = DOMUtils.getCursorPosition(this.currentEditingNote);
        
        // Store cursor position for after page reload
        if (cursorPosition) {
            localStorage.setItem('cursorPosition', JSON.stringify(cursorPosition));
        }
        
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
        const content = DOMUtils.getNoteContent(this.currentEditingNote);
        content.removeEventListener('mouseup', this.handleCursorChange);
        content.removeEventListener('keyup', this.handleCursorChange);
        
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
    },

    /**
     * Ensure any current edits are saved before performing an action
     */
    async ensureNotesSaved(action) {
        console.log('ensureNotesSaved:', {
            isAnyEditing: this.isAnyNoteEditing(),
            currentEditingNote: this.currentEditingNote,
            lastSavedContent: this.lastSavedContent,
            currentContent: this.currentEditingNote ? DOMUtils.getNoteContentText(this.currentEditingNote) : null
        });
        
        if (this.isAnyNoteEditing()) {
            console.log('Saving current note before action');
            await this.saveCurrentNote();
            console.log('Note saved');
        }
        console.log('Executing action');
        const result = await action();
        console.log('Action completed');
        return result;
    }
}; 